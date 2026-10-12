"""Drift detection: query-topic shift, embedding drift, quality decay (FR-O4).

Deterministic/offline pure helpers. Inputs are aggregates (topic counts, numeric scores, embedding
vectors); outputs carry only labels, numbers, and verdicts. Raw queries are never read or returned.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .auth import current_session, require_scope
from .core.errors import AppError

EPS = 1e-4
MAX_TOPICS = 1000
MAX_VECTORS = 5000
MAX_SCORES = 100_000


def _distribution(counts: dict[str, float], keys: Sequence[str], *, smooth: float = 0.0) -> list[float]:
    values = [max(float(counts.get(k, 0)), 0.0) + smooth for k in keys]
    total = sum(values)
    if total <= 0:
        raise ValueError("topic counts must contain at least one positive count")
    return [v / total for v in values]


def topic_shift(baseline: dict[str, float], current: dict[str, float]) -> dict[str, Any]:
    """Compare topic distributions: Jensen-Shannon divergence (base 2, 0..1) and PSI."""
    if sum(max(float(v), 0.0) for v in baseline.values()) <= 0 or sum(max(float(v), 0.0) for v in current.values()) <= 0:
        raise ValueError("topic counts must contain at least one positive count")
    keys = sorted(set(baseline) | set(current))
    p = _distribution(baseline, keys)
    q = _distribution(current, keys)
    m = [(a + b) / 2 for a, b in zip(p, q)]

    def kl(a: list[float], b: list[float]) -> float:
        return sum(x * math.log2(x / y) for x, y in zip(a, b) if x > 0 and y > 0)

    js = max(0.0, (kl(p, m) + kl(q, m)) / 2)
    ps, qs = _distribution(baseline, keys, smooth=EPS), _distribution(current, keys, smooth=EPS)
    psi = sum((b - a) * math.log(b / a) for a, b in zip(ps, qs))
    return {
        "js_divergence": round(js, 6),
        "psi": round(psi, 6),
        "new_topics": [k for k in keys if baseline.get(k, 0) <= 0 < current.get(k, 0)],
        "vanished_topics": [k for k in keys if current.get(k, 0) <= 0 < baseline.get(k, 0)],
    }


def _centroid(vectors: Sequence[Sequence[float]]) -> list[float]:
    dim = len(vectors[0])
    return [sum(v[i] for v in vectors) / len(vectors) for i in range(dim)]


def _norm(v: Sequence[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def embedding_drift(baseline: Sequence[Sequence[float]], current: Sequence[Sequence[float]]) -> dict[str, Any]:
    """Centroid cosine distance (0..2) and spread ratio (mean distance to centroid, current / baseline)."""
    if not baseline or not current:
        raise ValueError("embedding sets must not be empty")
    dim = len(baseline[0])
    if dim == 0 or any(len(v) != dim for v in baseline) or any(len(v) != dim for v in current):
        raise ValueError("embedding dimensions must match")
    cb, cc = _centroid(baseline), _centroid(current)
    nb, nc = _norm(cb), _norm(cc)
    if nb == 0 or nc == 0:
        raise ValueError("zero-length centroid")
    cosine = sum(a * b for a, b in zip(cb, cc)) / (nb * nc)
    distance = max(0.0, 1.0 - cosine)

    def spread(vectors: Sequence[Sequence[float]], c: list[float]) -> float:
        return sum(_norm([a - b for a, b in zip(v, c)]) for v in vectors) / len(vectors)

    sb, sc = spread(baseline, cb), spread(current, cc)
    ratio = sc / sb if sb > 0 else (1.0 if sc == 0 else float("inf"))
    return {
        "centroid_cosine_distance": round(distance, 6),
        "spread_ratio": round(ratio, 6) if math.isfinite(ratio) else 999.0,
        "n_baseline": len(baseline),
        "n_current": len(current),
    }


def quality_decay(
    baseline: Sequence[float], current: Sequence[float], *, max_drop: float = 0.05, min_samples: int = 30
) -> dict[str, Any]:
    """Mean-score drop of current vs baseline; not judged below `min_samples` on either side."""
    if max_drop < 0:
        raise ValueError("max_drop must be non-negative")
    n_b, n_c = len(baseline), len(current)
    if n_b < min_samples or n_c < min_samples:
        return {"decayed": False, "reason": "insufficient_samples", "drop": None, "n_baseline": n_b, "n_current": n_c}
    mb, mc = sum(baseline) / n_b, sum(current) / n_c
    drop = round(mb - mc, 6)
    return {
        "decayed": drop > max_drop, "reason": "quality_drop" if drop > max_drop else None,
        "drop": drop, "baseline_mean": round(mb, 4), "current_mean": round(mc, 4),
        "n_baseline": n_b, "n_current": n_c,
    }


def detect_drift(
    baseline: dict[str, Any],
    current: dict[str, Any],
    *,
    js_threshold: float = 0.1,
    psi_threshold: float = 0.25,
    embedding_threshold: float = 0.1,
    max_quality_drop: float = 0.05,
    min_samples: int = 30,
) -> dict[str, Any]:
    """Run every drift signal for which both windows supply data. Only allowlisted keys are read."""
    signals: dict[str, Any] = {}
    triggered: list[str] = []
    if baseline.get("topics") and current.get("topics"):
        res = topic_shift(baseline["topics"], current["topics"])
        res["triggered"] = res["js_divergence"] > js_threshold or res["psi"] > psi_threshold
        signals["topic_shift"] = res
        if res["triggered"]:
            triggered.append("topic_shift")
    if baseline.get("embeddings") and current.get("embeddings"):
        res = embedding_drift(baseline["embeddings"], current["embeddings"])
        res["triggered"] = res["centroid_cosine_distance"] > embedding_threshold
        signals["embedding_drift"] = res
        if res["triggered"]:
            triggered.append("embedding_drift")
    if baseline.get("scores") is not None and current.get("scores") is not None:
        res = quality_decay(baseline["scores"], current["scores"], max_drop=max_quality_drop, min_samples=min_samples)
        res["triggered"] = res["decayed"]
        signals["quality_decay"] = res
        if res["triggered"]:
            triggered.append("quality_decay")
    return {
        "drifted": bool(triggered),
        "signals_triggered": triggered,
        "signals": signals,
        "adapter_boundary": {"mode": "offline_local", "external_runners": ["evidently"], "imports_external_tools": False},
    }


class DriftWindow(BaseModel):
    topics: dict[str, float] | None = None
    scores: list[float] | None = None
    embeddings: list[list[float]] | None = None


class DriftIn(BaseModel):
    baseline: DriftWindow
    current: DriftWindow
    js_threshold: float = 0.1
    psi_threshold: float = 0.25
    embedding_threshold: float = 0.1
    max_quality_drop: float = 0.05
    min_samples: int = 30


router = APIRouter(prefix="/api/v1/operate", tags=["operate"])


@router.post("/drift")
async def drift_api(body: DriftIn, sess: dict = Depends(current_session)) -> dict[str, Any]:
    """FR-O4: compare a baseline window with the current window across topic/embedding/quality signals."""
    require_scope(sess, "evals")
    for w in (body.baseline, body.current):
        if (w.topics and len(w.topics) > MAX_TOPICS) or (w.embeddings and len(w.embeddings) > MAX_VECTORS) or (
            w.scores and len(w.scores) > MAX_SCORES
        ):
            raise AppError(400, "Drift window too large")
    try:
        return detect_drift(
            body.baseline.model_dump(exclude_none=True), body.current.model_dump(exclude_none=True),
            js_threshold=body.js_threshold, psi_threshold=body.psi_threshold,
            embedding_threshold=body.embedding_threshold, max_quality_drop=body.max_quality_drop,
            min_samples=body.min_samples,
        )
    except ValueError as exc:
        raise AppError(400, str(exc)) from exc
