"""Online evaluation on sampled production traffic (FR-O3).

Deterministic/offline. A sticky hash sampler (shared with the rollout bucketing) picks a share of
traces; a heuristic scorer rates each sampled trace from safe signals only (answered, has citation,
user feedback). A pluggable LLM-judge/Langfuse evaluator can replace the scorer later.

Only the allowlisted signal keys are read from a trace. Prompts, answers, and user ids are never read,
stored, or returned, so online eval cannot become a leakage channel.
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import current_session, require_scope
from .core.errors import AppError
from .db import EvalRun, get_session
from .eval_lab import _current_user, create_dataset
from .rollout import BUCKETS, bucket

MAX_FLAGGED_IDS = 100
MAX_TRACES = 100_000


def should_sample(trace_id: str, *, rate: float, salt: str) -> bool:
    """Sticky sampling: the same trace id always gets the same decision for a given salt."""
    if not 0.0 <= rate <= 1.0:
        raise ValueError("rate must be between 0 and 1")
    if rate >= 1.0:
        return True
    return bucket(salt, str(trace_id)) < rate * BUCKETS


def heuristic_score(trace: dict) -> dict[str, Any]:
    """Score one trace from safe signals only; 1.0 is best."""
    if not trace.get("answered", False):
        return {"score": 0.0, "flags": ["unanswered"]}
    score, flags = 1.0, []
    if not trace.get("has_citation", False):
        score -= 0.4
        flags.append("no_citation")
    if trace.get("feedback") == "down":
        score -= 0.4
        flags.append("negative_feedback")
    return {"score": round(max(score, 0.0), 4), "flags": flags}


def run_online_eval(
    traces: Sequence[dict],
    *,
    rate: float,
    salt: str = "online-eval",
    min_quality: float = 0.7,
    scorer: Callable[[dict], dict[str, Any]] = heuristic_score,
) -> dict[str, Any]:
    """Sample traces, score them, aggregate by bot version, and alert on low mean quality."""
    if not 0.0 <= min_quality <= 1.0:
        raise ValueError("min_quality must be between 0 and 1")
    grouped: dict[str, list[float]] = defaultdict(list)
    flag_counts: Counter[str] = Counter()
    flagged_ids: list[str] = []
    scores: list[float] = []
    for trace in traces:
        trace_id = str(trace.get("trace_id", ""))
        if not trace_id or not should_sample(trace_id, rate=rate, salt=salt):
            continue
        result = scorer(trace)
        scores.append(result["score"])
        grouped[str(trace.get("bot_version", "unknown"))[:80]].append(result["score"])
        if result["flags"]:
            flag_counts.update(result["flags"])
            if len(flagged_ids) < MAX_FLAGGED_IDS:
                flagged_ids.append(trace_id[:80])

    by_version = {
        version: {"n": len(values), "mean_score": round(sum(values) / len(values), 4)}
        for version, values in sorted(grouped.items())
    }
    mean = round(sum(scores) / len(scores), 4) if scores else None
    alert = mean is not None and mean < min_quality
    return {
        "total": len(traces),
        "sampled": len(scores),
        "sample_rate": rate,
        "mean_score": mean,
        "by_bot_version": by_version,
        "flag_counts": dict(sorted(flag_counts.items())),
        "trace_ids_flagged": flagged_ids,
        "min_quality": min_quality,
        "alert": alert,
        "alert_reason": "mean_quality_below_threshold" if alert else None,
        "adapter_boundary": {"mode": "offline_local", "external_runners": ["langfuse-evaluators"], "imports_external_tools": False},
    }


async def evaluate_online_traffic(
    session: AsyncSession,
    *,
    name: str,
    traces: Sequence[dict],
    rate: float,
    created_by: str,
    salt: str = "online-eval",
    min_quality: float = 0.7,
    dataset_id: uuid.UUID | None = None,
) -> EvalRun:
    """Run online eval over a trace batch and store a safe EvalRun (aggregates and trace ids only)."""
    if len(traces) > MAX_TRACES:
        raise AppError(400, "Too many traces")
    try:
        metrics = run_online_eval(traces, rate=rate, salt=salt, min_quality=min_quality)
    except ValueError as exc:
        raise AppError(400, str(exc)) from exc
    if dataset_id is None:
        ds = await create_dataset(
            session, name=name, items=[{"traces": len(traces), "rate": rate}], source="online_eval", created_by=created_by
        )
        dataset_id = ds.id
    run = EvalRun(
        dataset_id=dataset_id, adapter="online-eval.local", status="completed",
        metrics=metrics, item_results=[], created_by=created_by,
    )
    session.add(run)
    await session.commit()
    return run


class OnlineEvalIn(BaseModel):
    name: str = "online-eval"
    dataset_id: uuid.UUID | None = None
    traces: list[dict]
    rate: float = 0.1
    salt: str = "online-eval"
    min_quality: float = 0.7


router = APIRouter(prefix="/api/v1/evals", tags=["evals"])


@router.post("/online")
async def online_eval_api(
    body: OnlineEvalIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """FR-O3: score a sampled share of production traces and store a safe EvalRun."""
    from .auth import redis_client
    from .quotas import enforce_request_quota, get_effective_policy

    require_scope(sess, "evals")
    user = await _current_user(db, sess)
    policy = await get_effective_policy(db, user=user)
    await enforce_request_quota(redis_client(), user_id=sess["user_id"], endpoint="evals.online", policy=policy)
    # keep only allowlisted signal keys: prompts/answers/user ids are dropped before processing
    allowed = ("trace_id", "bot_version", "answered", "has_citation", "feedback")
    traces = [{k: t[k] for k in allowed if k in t} for t in body.traces]
    run = await evaluate_online_traffic(
        db, name=body.name, traces=traces, rate=body.rate, salt=body.salt, min_quality=body.min_quality,
        created_by=f"user:{user.id}", dataset_id=body.dataset_id,
    )
    return {"id": str(run.id), "adapter": run.adapter, "metrics": run.metrics}
