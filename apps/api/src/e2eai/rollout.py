"""Rollout strategies: shadow deploy, canary (traffic %), online A/B with feature flags (FR-RL4).

Pure/deterministic. Bucketing is a stable hash of (salt, subject) into 10,000 buckets, so one subject
always lands in the same arm and the split is reproducible. Shadow never changes the answer the user
sees: the baseline is always served and the candidate only runs on a sampled mirror. Plans and decisions
carry labels, versions, and percentages only (no prompts, answers, or user data).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .auth import current_session, require_scope
from .core.errors import AppError

STRATEGIES = ("canary", "shadow", "ab")
BUCKETS = 10_000


@dataclass
class RolloutPlan:
    strategy: str
    baseline: str
    candidate: str
    canary_percent: float = 0.0
    shadow_percent: float = 0.0
    ab_weights: dict[str, float] = field(default_factory=dict)
    salt: str = "rollout"
    enabled: bool = True  # feature flag: when off, everyone gets the baseline


def bucket(salt: str, subject: str) -> int:
    """Stable bucket in [0, 10000) for (salt, subject)."""
    digest = hashlib.sha256(f"{salt}:{subject}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % BUCKETS


def validate_plan(plan: RolloutPlan) -> RolloutPlan:
    if plan.strategy not in STRATEGIES:
        raise ValueError(f"strategy must be one of {STRATEGIES}")
    if not plan.baseline or not plan.candidate:
        raise ValueError("baseline and candidate are required")
    if plan.baseline == plan.candidate:
        raise ValueError("baseline and candidate must differ")
    if plan.strategy == "canary" and not 0 <= plan.canary_percent <= 100:
        raise ValueError("canary_percent must be between 0 and 100")
    if plan.strategy == "shadow" and not 0 <= plan.shadow_percent <= 100:
        raise ValueError("shadow_percent must be between 0 and 100")
    if plan.strategy == "ab":
        weights = plan.ab_weights
        if set(weights) != {plan.baseline, plan.candidate}:
            raise ValueError("ab_weights must cover exactly baseline and candidate")
        if any(w < 0 for w in weights.values()) or abs(sum(weights.values()) - 100) > 1e-6:
            raise ValueError("ab_weights must be non-negative and sum to 100")
    return plan


def assign(plan: RolloutPlan, subject: str) -> dict[str, Any]:
    """Decide which version serves `subject` and whether the candidate is mirrored (shadow)."""
    validate_plan(plan)
    if not plan.enabled:
        return {"serve": plan.baseline, "shadow": None, "arm": "baseline", "reason": "disabled"}
    position = bucket(plan.salt, subject)
    if plan.strategy == "canary":
        in_canary = position < plan.canary_percent * BUCKETS / 100
        return {
            "serve": plan.candidate if in_canary else plan.baseline,
            "shadow": None,
            "arm": "candidate" if in_canary else "baseline",
            "reason": "canary",
        }
    if plan.strategy == "shadow":
        mirrored = position < plan.shadow_percent * BUCKETS / 100
        return {
            "serve": plan.baseline,
            "shadow": plan.candidate if mirrored else None,
            "arm": "baseline",
            "reason": "shadow",
        }
    baseline_cut = plan.ab_weights[plan.baseline] * BUCKETS / 100
    in_baseline = position < baseline_cut
    return {
        "serve": plan.baseline if in_baseline else plan.candidate,
        "shadow": None,
        "arm": "baseline" if in_baseline else "candidate",
        "reason": "ab",
    }


def evaluate_promotion(
    *,
    baseline: dict[str, float],
    candidate: dict[str, float],
    min_samples: int = 200,
    max_quality_drop: float = 0.02,
    max_error_increase: float = 0.005,
) -> dict[str, Any]:
    """promote when enough data and no regression; rollback on regression; else keep collecting."""
    if candidate.get("n", 0) < min_samples or baseline.get("n", 0) < min_samples:
        return {"decision": "continue", "reasons": ["insufficient_samples"]}
    reasons: list[str] = []
    if baseline["quality"] - candidate["quality"] > max_quality_drop:
        reasons.append("quality_drop")
    if candidate["error_rate"] - baseline["error_rate"] > max_error_increase:
        reasons.append("error_rate_increase")
    return {"decision": "rollback" if reasons else "promote", "reasons": reasons}


class AssignIn(BaseModel):
    strategy: str
    baseline: str
    candidate: str
    canary_percent: float = 0.0
    shadow_percent: float = 0.0
    ab_weights: dict[str, float] = {}
    salt: str = "rollout"
    enabled: bool = True
    subject: str


class PromotionIn(BaseModel):
    baseline: dict[str, float]
    candidate: dict[str, float]
    min_samples: int = 200
    max_quality_drop: float = 0.02
    max_error_increase: float = 0.005


router = APIRouter(prefix="/api/v1/rollouts", tags=["rollouts"])


@router.post("/assign")
async def assign_api(body: AssignIn, sess: dict = Depends(current_session)) -> dict[str, Any]:
    """FR-RL4: which bundle version serves a subject under a rollout plan."""
    require_scope(sess, "bots")
    plan = RolloutPlan(
        strategy=body.strategy, baseline=body.baseline, candidate=body.candidate,
        canary_percent=body.canary_percent, shadow_percent=body.shadow_percent,
        ab_weights=dict(body.ab_weights), salt=body.salt, enabled=body.enabled,
    )
    try:
        return assign(plan, body.subject)
    except ValueError as exc:
        raise AppError(400, str(exc)) from exc


@router.post("/promotion")
async def promotion_api(body: PromotionIn, sess: dict = Depends(current_session)) -> dict[str, Any]:
    """FR-RL4: promote / continue / rollback decision from online arm metrics."""
    require_scope(sess, "bots")
    try:
        return evaluate_promotion(
            baseline=body.baseline, candidate=body.candidate, min_samples=body.min_samples,
            max_quality_drop=body.max_quality_drop, max_error_increase=body.max_error_increase,
        )
    except KeyError as exc:
        raise AppError(400, "baseline and candidate need n, quality and error_rate") from exc
