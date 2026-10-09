"""Benchmark runner: model x prompt x dataset leaderboard (FR-T11).

Deterministic/offline: per-combination measurement samples are supplied by the caller (quality,
latency, TTFT, tokens, cost). This module aggregates them into a leaderboard with quality,
p50/p95 latency, TTFT, tokens/s, and cost, then stores a normalized EvalRun.

ponytail: samples are injected rather than measured live. A live runner that executes
model x prompt x dataset through the chat path can populate `samples` and reuse this aggregation
untouched; the stored run shape stays stable.
"""

import math
import uuid
from collections.abc import Sequence

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import current_session, require_scope
from .db import EvalRun, get_session
from .eval_lab import _current_user


def _percentile(values: Sequence[float], p: float) -> float:
    """Linear-interpolation percentile (numpy default). Empty -> 0.0."""
    if not values:
        return 0.0
    s = sorted(float(v) for v in values)
    if len(s) == 1:
        return s[0]
    rank = (p / 100.0) * (len(s) - 1)
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return s[lo]
    return s[lo] + (s[hi] - s[lo]) * (rank - lo)


def summarize_combination(combo: dict) -> dict:
    """Aggregate one model x prompt x dataset combination into a safe leaderboard row.

    Only measurement numbers and the combination labels are kept — never raw answers/snippets.
    """
    samples = combo.get("samples") or []
    qualities = [float(s.get("quality", 0.0) or 0.0) for s in samples]
    latencies = [float(s["latency_ms"]) for s in samples if s.get("latency_ms") is not None]
    ttfts = [float(s["ttft_ms"]) for s in samples if s.get("ttft_ms") is not None]
    tok_per_s = []
    for s in samples:
        tok = float(s.get("output_tokens") or 0.0)
        lat_ms = float(s.get("latency_ms") or 0.0)
        if tok and lat_ms:
            tok_per_s.append(tok / (lat_ms / 1000.0))
    return {
        "model": combo.get("model"),
        "prompt": combo.get("prompt"),
        "dataset": combo.get("dataset"),
        "samples": len(samples),
        "quality": round(sum(qualities) / len(qualities), 4) if qualities else 0.0,
        "latency_p50_ms": round(_percentile(latencies, 50), 4),
        "latency_p95_ms": round(_percentile(latencies, 95), 4),
        "ttft_p50_ms": round(_percentile(ttfts, 50), 4),
        "ttft_p95_ms": round(_percentile(ttfts, 95), 4),
        "tokens_per_s": round(sum(tok_per_s) / len(tok_per_s), 4) if tok_per_s else 0.0,
        "cost_usd": round(sum(float(s.get("cost_usd") or 0.0) for s in samples), 6),
    }


def build_benchmark_leaderboard(combinations: Sequence[dict]) -> list[dict]:
    """Rank combinations: best quality first, ties broken by lower p50 latency then lower cost."""
    rows = [summarize_combination(c) for c in combinations]
    return sorted(
        rows,
        key=lambda r: (
            -r["quality"],
            r["latency_p50_ms"],
            r["cost_usd"],
            str(r["model"]),
            str(r["prompt"]),
            str(r["dataset"]),
        ),
    )


async def run_benchmark(
    session: AsyncSession,
    *,
    name: str,
    combinations: Sequence[dict],
    created_by: str,
    dataset_id: uuid.UUID | None = None,
) -> EvalRun:
    leaderboard = build_benchmark_leaderboard(combinations)
    metrics = {
        "name": name,
        "combinations": len(leaderboard),
        "models": sorted({r["model"] for r in leaderboard if r["model"]}),
        "prompts": sorted({r["prompt"] for r in leaderboard if r["prompt"]}),
        "datasets": sorted({r["dataset"] for r in leaderboard if r["dataset"]}),
        "best": leaderboard[0] if leaderboard else None,
        "total_cost_usd": round(sum(r["cost_usd"] for r in leaderboard), 6),
    }
    run = EvalRun(
        dataset_id=dataset_id,
        adapter="benchmark.local",
        status="completed",
        metrics=metrics,
        item_results=leaderboard,
        created_by=created_by,
    )
    session.add(run)
    await session.commit()
    return run


class BenchmarkSampleIn(BaseModel):
    quality: float = 0.0
    latency_ms: float | None = None
    ttft_ms: float | None = None
    output_tokens: float | None = None
    cost_usd: float = 0.0


class BenchmarkComboIn(BaseModel):
    model: str
    prompt: str
    dataset: str
    samples: list[BenchmarkSampleIn] = []


class BenchmarkIn(BaseModel):
    name: str = "benchmark"
    dataset_id: uuid.UUID | None = None
    combinations: list[BenchmarkComboIn]


router = APIRouter(prefix="/api/v1/evals", tags=["evals"])


@router.post("/benchmark")
async def run_benchmark_api(
    body: BenchmarkIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """FR-T11: run a model x prompt x dataset benchmark and store the leaderboard as an EvalRun."""
    from .auth import redis_client
    from .quotas import enforce_request_quota, get_effective_policy

    require_scope(sess, "evals")
    user = await _current_user(db, sess)

    policy = await get_effective_policy(db, user=user)
    await enforce_request_quota(redis_client(), user_id=sess["user_id"], endpoint="evals.benchmark", policy=policy)

    combinations = [c.model_dump() for c in body.combinations]
    run = await run_benchmark(
        db,
        name=body.name,
        combinations=combinations,
        created_by=f"user:{user.id}",
        dataset_id=body.dataset_id,
    )
    return {"id": str(run.id), "adapter": run.adapter, "metrics": run.metrics, "item_results": run.item_results}
