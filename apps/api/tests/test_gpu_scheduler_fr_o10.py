"""FR-O10 GPU scheduling and sharing (Kueue-style queues, NVIDIA MIG / time-slicing).

Deterministic/offline planner: given a GPU inventory and a list of workload requests it decides which
workload gets which GPU (or MIG slice / time-slice share), respecting priority, per-team quotas, and
memory fit; whatever cannot run is queued with a reason. It never talks to Kubernetes or a driver.
"""

import pytest


def _gpus():
    return [
        {"id": "gpu0", "memory_gb": 80, "mig_profiles": ["1g.10gb", "2g.20gb", "3g.40gb"], "mig_enabled": True},
        {"id": "gpu1", "memory_gb": 24, "mig_profiles": [], "mig_enabled": False},
    ]


def test_inventory_validation():
    from e2eai.gpu_scheduler import validate_inventory

    inv = validate_inventory(_gpus())
    assert [g["id"] for g in inv] == ["gpu0", "gpu1"]
    for bad in (
        [],
        [{"id": "a", "memory_gb": 0}],
        [{"id": "a", "memory_gb": 8}, {"id": "a", "memory_gb": 8}],
        [{"id": "a", "memory_gb": 8, "mig_enabled": True, "mig_profiles": ["9g.999gb"]}],
        [{"id": "", "memory_gb": 8}],
    ):
        with pytest.raises(ValueError):
            validate_inventory(bad)


def test_exclusive_workload_gets_smallest_gpu_that_fits():
    from e2eai.gpu_scheduler import schedule

    res = schedule(_gpus(), [{"id": "w1", "team": "ml", "memory_gb": 20, "sharing": "exclusive", "priority": 5}])
    a = res["assignments"][0]
    assert a["workload_id"] == "w1" and a["gpu_id"] == "gpu1" and a["mode"] == "exclusive"
    assert res["queued"] == []


def test_mig_slices_pack_small_workloads_onto_a_mig_gpu():
    from e2eai.gpu_scheduler import schedule

    wl = [{"id": f"w{i}", "team": "ml", "memory_gb": 8, "sharing": "mig", "priority": 1} for i in range(3)]
    res = schedule(_gpus(), wl)
    assert {a["gpu_id"] for a in res["assignments"]} == {"gpu0"}
    assert all(a["mode"] == "mig" and a["mig_profile"] == "1g.10gb" for a in res["assignments"])
    # a workload needing 30 GB gets the 3g.40gb slice (smallest profile that fits)
    big = schedule(_gpus(), [{"id": "b", "team": "ml", "memory_gb": 30, "sharing": "mig", "priority": 1}])
    assert big["assignments"][0]["mig_profile"] == "3g.40gb"


def test_mig_not_available_on_non_mig_gpu_and_queues_with_reason():
    from e2eai.gpu_scheduler import schedule

    inv = [{"id": "gpu1", "memory_gb": 24, "mig_profiles": [], "mig_enabled": False}]
    res = schedule(inv, [{"id": "w", "team": "ml", "memory_gb": 8, "sharing": "mig", "priority": 1}])
    assert res["assignments"] == [] and res["queued"][0] == {"workload_id": "w", "reason": "no_mig_capacity"}


def test_time_slicing_shares_a_gpu_up_to_memory_capacity():
    from e2eai.gpu_scheduler import schedule

    inv = [{"id": "gpu1", "memory_gb": 24, "mig_profiles": [], "mig_enabled": False}]
    wl = [{"id": f"t{i}", "team": "ml", "memory_gb": 10, "sharing": "time_slice", "priority": 1} for i in range(3)]
    res = schedule(inv, wl)
    assert len(res["assignments"]) == 2 and all(a["mode"] == "time_slice" for a in res["assignments"])
    assert res["queued"] == [{"workload_id": "t2", "reason": "insufficient_memory"}]
    assert [a["share"] for a in res["assignments"]] == [0.5, 0.5]


def test_priority_order_then_fifo_and_quota_enforced_per_team():
    from e2eai.gpu_scheduler import schedule

    inv = [{"id": "gpu1", "memory_gb": 24, "mig_profiles": [], "mig_enabled": False}]
    wl = [
        {"id": "low", "team": "a", "memory_gb": 20, "sharing": "exclusive", "priority": 1},
        {"id": "high", "team": "b", "memory_gb": 20, "sharing": "exclusive", "priority": 9},
    ]
    res = schedule(inv, wl)
    assert [a["workload_id"] for a in res["assignments"]] == ["high"]
    assert res["queued"] == [{"workload_id": "low", "reason": "no_free_gpu"}]

    quota = schedule(_gpus(), [
        {"id": "q1", "team": "a", "memory_gb": 20, "sharing": "exclusive", "priority": 1},
        {"id": "q2", "team": "a", "memory_gb": 70, "sharing": "exclusive", "priority": 1},
    ], team_quota_gb={"a": 30})
    assert [a["workload_id"] for a in quota["assignments"]] == ["q1"]
    assert quota["queued"] == [{"workload_id": "q2", "reason": "team_quota_exceeded"}]


def test_workload_larger_than_any_gpu_is_rejected_and_utilization_reported():
    from e2eai.gpu_scheduler import schedule

    res = schedule(_gpus(), [
        {"id": "huge", "team": "ml", "memory_gb": 200, "sharing": "exclusive", "priority": 1},
        {"id": "ok", "team": "ml", "memory_gb": 70, "sharing": "exclusive", "priority": 1},
    ])
    assert {"workload_id": "huge", "reason": "exceeds_largest_gpu"} in res["queued"]
    util = {u["gpu_id"]: u for u in res["utilization"]}
    assert util["gpu0"]["used_gb"] == 80 and util["gpu0"]["free_gb"] == 0
    assert util["gpu1"]["used_gb"] == 0
    for bad in ({"id": "x", "team": "t", "memory_gb": -1, "sharing": "exclusive", "priority": 1},
                {"id": "x", "team": "t", "memory_gb": 5, "sharing": "magic", "priority": 1}):
        with pytest.raises(ValueError):
            schedule(_gpus(), [bad])


def test_route_wired():
    from e2eai.main import app

    assert "post" in app.openapi()["paths"]["/api/v1/operate/gpu-schedule"]
