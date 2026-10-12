"""FR-RL4 rollout strategies: shadow deploy, canary (traffic %), online A/B with feature flags.

Pure/deterministic: bucketing is a stable hash of (salt, subject), so the same user always lands in
the same arm. Shadow never changes the user-visible answer. Plans are validated and metadata-only.
"""

import pytest


def test_bucket_is_stable_uniform_and_salted():
    from e2eai.rollout import bucket

    assert bucket("rollout-1", "user-a") == bucket("rollout-1", "user-a")
    assert 0 <= bucket("rollout-1", "user-a") < 10_000
    assert bucket("rollout-1", "user-a") != bucket("rollout-2", "user-a") or bucket("rollout-1", "user-b") != bucket("rollout-2", "user-b")
    counts = sum(1 for i in range(4000) if bucket("salt", f"u{i}") < 2500)
    assert 800 < counts < 1200  # ~25% of 4000


def test_canary_routes_expected_share_and_is_sticky():
    from e2eai.rollout import RolloutPlan, assign

    plan = RolloutPlan(strategy="canary", baseline="v1", candidate="v2", canary_percent=10, salt="r1")
    results = [assign(plan, f"user-{i}") for i in range(5000)]
    share = sum(1 for r in results if r["serve"] == "v2") / 5000
    assert 0.07 < share < 0.13
    assert all(r["shadow"] is None for r in results)
    assert assign(plan, "user-42") == assign(plan, "user-42")

    zero = RolloutPlan(strategy="canary", baseline="v1", candidate="v2", canary_percent=0, salt="r1")
    assert all(assign(zero, f"u{i}")["serve"] == "v1" for i in range(200))
    full = RolloutPlan(strategy="canary", baseline="v1", candidate="v2", canary_percent=100, salt="r1")
    assert all(assign(full, f"u{i}")["serve"] == "v2" for i in range(200))


def test_shadow_always_serves_baseline_and_mirrors_sampled_traffic():
    from e2eai.rollout import RolloutPlan, assign

    plan = RolloutPlan(strategy="shadow", baseline="v1", candidate="v2", shadow_percent=30, salt="s1")
    results = [assign(plan, f"u{i}") for i in range(4000)]
    assert all(r["serve"] == "v1" for r in results)  # users never see the candidate
    mirrored = sum(1 for r in results if r["shadow"] == "v2") / 4000
    assert 0.25 < mirrored < 0.35
    assert all(r["shadow"] in (None, "v2") for r in results)


def test_ab_test_splits_by_weights_and_respects_feature_flag():
    from e2eai.rollout import RolloutPlan, assign

    plan = RolloutPlan(strategy="ab", baseline="v1", candidate="v2", ab_weights={"v1": 50, "v2": 50}, salt="a1")
    served = [assign(plan, f"u{i}")["serve"] for i in range(4000)]
    assert 0.45 < served.count("v2") / 4000 < 0.55
    assert set(served) == {"v1", "v2"}

    off = RolloutPlan(strategy="ab", baseline="v1", candidate="v2", ab_weights={"v1": 50, "v2": 50}, salt="a1", enabled=False)
    assert all(assign(off, f"u{i}") == {"serve": "v1", "shadow": None, "arm": "baseline", "reason": "disabled"} for i in range(50))


def test_plan_validation_rejects_bad_configurations():
    from e2eai.rollout import RolloutPlan, validate_plan

    for bad in (
        RolloutPlan(strategy="blue-green", baseline="v1", candidate="v2"),
        RolloutPlan(strategy="canary", baseline="v1", candidate="v1", canary_percent=5),
        RolloutPlan(strategy="canary", baseline="v1", candidate="v2", canary_percent=101),
        RolloutPlan(strategy="shadow", baseline="v1", candidate="v2", shadow_percent=-1),
        RolloutPlan(strategy="ab", baseline="v1", candidate="v2", ab_weights={"v1": 60, "v2": 30}),
        RolloutPlan(strategy="ab", baseline="v1", candidate="v2", ab_weights={"v1": 50, "v3": 50}),
        RolloutPlan(strategy="canary", baseline="", candidate="v2"),
    ):
        with pytest.raises(ValueError):
            validate_plan(bad)


def test_promotion_decision_requires_enough_samples_and_no_regression():
    from e2eai.rollout import evaluate_promotion

    ok = evaluate_promotion(
        baseline={"n": 500, "quality": 0.80, "error_rate": 0.01},
        candidate={"n": 400, "quality": 0.82, "error_rate": 0.01},
        min_samples=200, max_quality_drop=0.02, max_error_increase=0.005,
    )
    assert ok == {"decision": "promote", "reasons": []}

    few = evaluate_promotion(
        baseline={"n": 500, "quality": 0.8, "error_rate": 0.01}, candidate={"n": 50, "quality": 0.9, "error_rate": 0.0},
        min_samples=200, max_quality_drop=0.02, max_error_increase=0.005,
    )
    assert few["decision"] == "continue" and few["reasons"] == ["insufficient_samples"]

    bad = evaluate_promotion(
        baseline={"n": 500, "quality": 0.80, "error_rate": 0.01}, candidate={"n": 500, "quality": 0.70, "error_rate": 0.05},
        min_samples=200, max_quality_drop=0.02, max_error_increase=0.005,
    )
    assert bad["decision"] == "rollback"
    assert sorted(bad["reasons"]) == ["error_rate_increase", "quality_drop"]


def test_routes_are_wired():
    from e2eai.main import app

    paths = app.openapi()["paths"]
    assert "post" in paths["/api/v1/rollouts/assign"]
    assert "post" in paths["/api/v1/rollouts/promotion"]
