"""GPU scheduling and sharing planner (FR-O10).

Deterministic/offline, Kueue-style: workloads are admitted by priority (then request order), subject to
per-team memory quotas, and placed on a GPU exclusively, on a MIG slice, or by time-slicing. Whatever
cannot run is queued with a reason code. This module never talks to Kubernetes or a driver; the plan it
returns is what a Kueue/device-plugin adapter would apply. Output carries ids, teams, and numbers only.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .auth import current_session, require_scope
from .core.errors import AppError

# NVIDIA MIG profile name -> slice memory in GB (A100 40GB / 80GB families).
MIG_PROFILE_GB: dict[str, int] = {
    "1g.5gb": 5, "2g.10gb": 10, "3g.20gb": 20, "4g.20gb": 20, "7g.40gb": 40,
    "1g.10gb": 10, "2g.20gb": 20, "3g.40gb": 40, "4g.40gb": 40, "7g.80gb": 80,
}
SHARING_MODES = {"exclusive", "mig", "time_slice"}
MAX_GPUS = 64
MAX_WORKLOADS = 500


def validate_inventory(gpus: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(gpus, list) or not gpus or len(gpus) > MAX_GPUS:
        raise ValueError("inventory needs between 1 and 64 GPUs")
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for g in gpus:
        gid = g.get("id") if isinstance(g, dict) else None
        if not isinstance(gid, str) or not gid.strip():
            raise ValueError("GPU needs an id")
        if gid in seen:
            raise ValueError("duplicate GPU id")
        seen.add(gid)
        mem = g.get("memory_gb")
        if isinstance(mem, bool) or not isinstance(mem, (int, float)) or mem <= 0:
            raise ValueError("memory_gb must be positive")
        profiles = list(g.get("mig_profiles") or [])
        for p in profiles:
            if p not in MIG_PROFILE_GB or MIG_PROFILE_GB[p] > mem:
                raise ValueError("unsupported MIG profile")
        out.append({
            "id": gid, "memory_gb": float(mem),
            "mig_profiles": sorted(profiles, key=lambda p: MIG_PROFILE_GB[p]),
            "mig_enabled": bool(g.get("mig_enabled")) and bool(profiles),
        })
    return out


def _validate_workloads(workloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(workloads, list) or len(workloads) > MAX_WORKLOADS:
        raise ValueError("too many workloads")
    seen: set[str] = set()
    out = []
    for i, w in enumerate(workloads):
        wid, team = w.get("id"), w.get("team")
        if not isinstance(wid, str) or not wid.strip() or not isinstance(team, str) or not team.strip():
            raise ValueError("workload needs an id and a team")
        if wid in seen:
            raise ValueError("duplicate workload id")
        seen.add(wid)
        mem = w.get("memory_gb")
        if isinstance(mem, bool) or not isinstance(mem, (int, float)) or mem <= 0:
            raise ValueError("memory_gb must be positive")
        if w.get("sharing", "exclusive") not in SHARING_MODES:
            raise ValueError("unsupported sharing mode")
        prio = w.get("priority", 0)
        if isinstance(prio, bool) or not isinstance(prio, int):
            raise ValueError("priority must be an integer")
        out.append({"id": wid, "team": team, "memory_gb": float(mem),
                    "sharing": w.get("sharing", "exclusive"), "priority": prio, "_order": i})
    return out


def schedule(
    gpus: list[dict[str, Any]],
    workloads: list[dict[str, Any]],
    *,
    team_quota_gb: dict[str, float] | None = None,
) -> dict[str, Any]:
    inventory = validate_inventory(gpus)
    queue = sorted(_validate_workloads(workloads), key=lambda w: (-w["priority"], w["_order"]))
    quota = team_quota_gb or {}
    state = {g["id"]: {"gpu": g, "mode": None, "slices": [], "tenants": []} for g in inventory}
    largest = max(g["memory_gb"] for g in inventory)
    team_used: dict[str, float] = {}
    assignments: list[dict[str, Any]] = []
    queued: list[dict[str, Any]] = []

    def used_gb(st: dict[str, Any]) -> float:
        if st["mode"] == "exclusive":
            return st["gpu"]["memory_gb"]
        if st["mode"] == "mig":
            return float(sum(MIG_PROFILE_GB[p] for p in st["slices"]))
        if st["mode"] == "time_slice":
            return float(sum(m for _, m in st["tenants"]))
        return 0.0

    for w in queue:
        wid, team, mem = w["id"], w["team"], w["memory_gb"]
        if mem > largest:
            queued.append({"workload_id": wid, "reason": "exceeds_largest_gpu"})
            continue
        limit = quota.get(team)
        if limit is not None and team_used.get(team, 0.0) + mem > limit:
            queued.append({"workload_id": wid, "reason": "team_quota_exceeded"})
            continue

        placed: dict[str, Any] | None = None
        reason = "no_free_gpu"
        if w["sharing"] == "exclusive":
            free = [s for s in state.values() if s["mode"] is None and s["gpu"]["memory_gb"] >= mem]
            if free:
                st = min(free, key=lambda s: s["gpu"]["memory_gb"])
                st["mode"] = "exclusive"
                placed = {"workload_id": wid, "gpu_id": st["gpu"]["id"], "mode": "exclusive"}
        elif w["sharing"] == "mig":
            reason = "no_mig_capacity"
            for st in sorted(state.values(), key=lambda s: (s["mode"] != "mig", s["gpu"]["id"])):
                if not st["gpu"]["mig_enabled"] or st["mode"] not in (None, "mig"):
                    continue
                fits = [p for p in st["gpu"]["mig_profiles"] if MIG_PROFILE_GB[p] >= mem]
                if not fits:
                    continue
                profile = fits[0]
                if used_gb(st) + MIG_PROFILE_GB[profile] > st["gpu"]["memory_gb"]:
                    continue
                st["mode"] = "mig"
                st["slices"].append(profile)
                placed = {"workload_id": wid, "gpu_id": st["gpu"]["id"], "mode": "mig", "mig_profile": profile}
                break
        else:  # time_slice
            candidates = [s for s in state.values() if s["mode"] in (None, "time_slice")]
            reason = "no_free_gpu" if not candidates else "insufficient_memory"
            fits = [s for s in candidates if s["gpu"]["memory_gb"] - used_gb(s) >= mem]
            if fits:
                st = min(fits, key=lambda s: s["gpu"]["memory_gb"] - used_gb(s))
                st["mode"] = "time_slice"
                st["tenants"].append((wid, mem))
                placed = {"workload_id": wid, "gpu_id": st["gpu"]["id"], "mode": "time_slice"}

        if placed is None:
            queued.append({"workload_id": wid, "reason": reason})
            continue
        placed["memory_gb"] = mem
        assignments.append(placed)
        team_used[team] = team_used.get(team, 0.0) + mem

    for a in assignments:  # share is final: equal time slices among a GPU's tenants
        if a["mode"] == "time_slice":
            a["share"] = round(1.0 / len(state[a["gpu_id"]]["tenants"]), 4)

    utilization = []
    for st in state.values():
        total = st["gpu"]["memory_gb"]
        used = used_gb(st)
        utilization.append({
            "gpu_id": st["gpu"]["id"], "mode": st["mode"], "memory_gb": total,
            "used_gb": used, "free_gb": round(total - used, 3),
            "tenants": len(st["tenants"]) + len(st["slices"]) + (1 if st["mode"] == "exclusive" else 0),
        })
    return {"assignments": assignments, "queued": queued, "utilization": utilization}


class GpuIn(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    memory_gb: float
    mig_profiles: list[str] = []
    mig_enabled: bool = False


class WorkloadIn(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    team: str = Field(min_length=1, max_length=100)
    memory_gb: float
    sharing: str = Field(default="exclusive", max_length=20)
    priority: int = 0


class GpuScheduleIn(BaseModel):
    gpus: list[GpuIn] = Field(max_length=MAX_GPUS)
    workloads: list[WorkloadIn] = Field(max_length=MAX_WORKLOADS)
    team_quota_gb: dict[str, float] = {}


router = APIRouter(prefix="/api/v1/operate", tags=["operate"])


@router.post("/gpu-schedule")
async def gpu_schedule_api(body: GpuScheduleIn, sess: dict = Depends(current_session)) -> dict[str, Any]:
    """FR-O10: plan GPU placement (exclusive / MIG / time-slice) with priorities and team quotas."""
    require_scope(sess, "evals")
    try:
        return schedule(
            [g.model_dump() for g in body.gpus], [w.model_dump() for w in body.workloads],
            team_quota_gb=body.team_quota_gb,
        )
    except ValueError as exc:
        raise AppError(400, str(exc)) from exc
