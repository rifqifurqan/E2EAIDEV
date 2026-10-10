"""SLO window metrics and alert firing decisions (FR-O5).

Computes latency (p50/p95/mean), error rate, cost per conversation, and guardrail trigger rate
from already-recorded chat/message/guardrail/audit-like event inputs. Outputs are safe: only
aggregated metrics and alert metadata — never raw prompts, answers, document text, restricted
titles/snippets, secrets, tokens, or credentials.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import current_session, require_scope
from .core.errors import AppError
from .db import get_session


@dataclass(frozen=True)
class SloPolicy:
    """Configurable SLO thresholds (FR-O5).

    Each field sets the maximum acceptable value; exceeding it fires an alert.
    """

    latency_p50_ms: float = 500.0
    latency_p95_ms: float = 2000.0
    error_rate: float = 0.05
    cost_per_conversation_usd: float = 0.05
    guardrail_trigger_rate: float = 0.10


def _percentile(sorted_values: Sequence[float], p: float) -> float:
    """Nearest-rank percentile on a pre-sorted list. Returns 0.0 for empty input."""
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    # Linear interpolation between nearest ranks
    rank = (p / 100.0) * (n - 1)
    lower = int(math.floor(rank))
    upper = min(lower + 1, n - 1)
    fraction = rank - lower
    return round(sorted_values[lower] + fraction * (sorted_values[upper] - sorted_values[lower]), 4)


def compute_slo_metrics(events: Sequence[dict]) -> dict:
    """Compute SLO window metrics from event records.

    Each event dict should have at minimum:
        latency_ms (int|float), error (bool), cost_usd (float), guardrail_triggered (bool).

    Returns aggregated metrics only — no raw content, prompts, answers, or secrets.
    """
    n = len(events)
    if n == 0:
        return {
            "total_events": 0,
            "latency_p50_ms": 0.0,
            "latency_p95_ms": 0.0,
            "latency_mean_ms": 0.0,
            "error_rate": 0.0,
            "cost_per_conversation_usd": 0.0,
            "guardrail_trigger_rate": 0.0,
        }

    latencies = sorted(float(e.get("latency_ms", 0)) for e in events)
    errors = sum(1 for e in events if e.get("error"))
    total_cost = sum(float(e.get("cost_usd", 0)) for e in events)
    guardrail_triggers = sum(1 for e in events if e.get("guardrail_triggered"))

    return {
        "total_events": n,
        "latency_p50_ms": _percentile(latencies, 50),
        "latency_p95_ms": _percentile(latencies, 95),
        "latency_mean_ms": round(sum(latencies) / n, 4),
        "error_rate": round(errors / n, 4),
        "cost_per_conversation_usd": round(total_cost / n, 4),
        "guardrail_trigger_rate": round(guardrail_triggers / n, 4),
    }


def check_slo_alerts(metrics: dict, policy: SloPolicy) -> dict:
    """Evaluate alert firing decisions against SLO thresholds.

    Returns a dict with ``any_firing`` (bool), ``total_checked`` (int), and ``alerts`` (list of
    fired alerts with name, actual, threshold). Output is safe: only metric names and numbers.
    """
    checks = [
        ("latency_p50", metrics.get("latency_p50_ms", 0.0), policy.latency_p50_ms),
        ("latency_p95", metrics.get("latency_p95_ms", 0.0), policy.latency_p95_ms),
        ("error_rate", metrics.get("error_rate", 0.0), policy.error_rate),
        ("cost_per_conversation", metrics.get("cost_per_conversation_usd", 0.0), policy.cost_per_conversation_usd),
        ("guardrail_trigger_rate", metrics.get("guardrail_trigger_rate", 0.0), policy.guardrail_trigger_rate),
    ]

    fired = []
    for name, actual, threshold in checks:
        if actual > threshold:
            fired.append({"name": name, "actual": actual, "threshold": threshold})

    return {
        "any_firing": len(fired) > 0,
        "total_checked": len(checks),
        "alerts": fired,
    }


# ---------------------------------------------------------------------------
# API route (FR-O5)
# ---------------------------------------------------------------------------


class SloMetricsIn(BaseModel):
    events: list[dict]
    policy: dict | None = None


router = APIRouter(prefix="/api/v1/operate", tags=["operate"])


@router.post("/slo-metrics")
async def slo_metrics_api(
    body: SloMetricsIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """FR-O5: compute SLO window metrics and alert firing decisions.

    Accepts event records and an optional policy override. Returns aggregated metrics
    and alert metadata only — never raw prompts, answers, or secrets.
    """
    require_scope(sess, "evals")

    policy = SloPolicy()
    if body.policy:
        policy = SloPolicy(
            latency_p50_ms=float(body.policy.get("latency_p50_ms", policy.latency_p50_ms)),
            latency_p95_ms=float(body.policy.get("latency_p95_ms", policy.latency_p95_ms)),
            error_rate=float(body.policy.get("error_rate", policy.error_rate)),
            cost_per_conversation_usd=float(body.policy.get("cost_per_conversation_usd", policy.cost_per_conversation_usd)),
            guardrail_trigger_rate=float(body.policy.get("guardrail_trigger_rate", policy.guardrail_trigger_rate)),
        )

    if not body.events:
        raise AppError(400, "Events list is required")

    metrics = compute_slo_metrics(body.events)
    alerts = check_slo_alerts(metrics, policy)

    return {"metrics": metrics, "alerts": alerts}
