"""SLO window metrics and alert firing decisions (FR-O5).

Computes latency (p50/p95/mean), error rate, cost per conversation, and guardrail trigger rate
from already-recorded chat/message/guardrail/audit-like event inputs. Outputs are safe: only
aggregated metrics and alert metadata — never raw prompts, answers, document text, restricted
titles/snippets, secrets, tokens, or credentials.
"""

import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import current_session, require_scope
from .core.errors import AppError
from .db import AuditEntry, Message, Notification, Role, SloAlert, User, UserRole, get_session

# Conservative token cost estimate; real cost depends on the LiteLLM model/provider.
# ponytail: replace with per-model cost lookup when billing metadata is available (FR-O6).
_TOKEN_COST_USD: float = 2e-6  # 0.000002 USD/token ≈ $2/1M tokens


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
# DB-backed window aggregation (FR-O5)
# ---------------------------------------------------------------------------


async def aggregate_slo_events_from_db(
    session: AsyncSession,
    window_start: datetime,
    window_end: datetime,
) -> list[dict]:
    """Aggregate SLO events from persisted assistant Message rows and retrieval guardrail
    audit entries in a time window.

    Message events: reads only latency_ms, tokens, stop_reason — never content, role, model,
    or any credential. guardrail_triggered=False for these rows.

    Guardrail events: counts AuditEntry rows where action == 'retrieval.context.blocked'
    and at is within the window. Each matched entry becomes a synthetic safe event with
    latency_ms=0, error=False, cost_usd=0.0, guardrail_triggered=True. AuditEntry.details
    are never read or included.

    Returns a list of safe event dicts compatible with ``compute_slo_metrics``.
    """
    message_rows = (
        await session.execute(
            select(Message.latency_ms, Message.tokens, Message.stop_reason)
            .where(Message.role == "assistant")
            .where(Message.created_at >= window_start)
            .where(Message.created_at <= window_end)
        )
    ).all()

    events: list[dict] = []
    for row in message_rows:
        events.append({
            "latency_ms": row.latency_ms or 0,
            "error": row.stop_reason == "error",
            "cost_usd": (row.tokens or 0) * _TOKEN_COST_USD,
            "guardrail_triggered": False,
        })

    guardrail_count: int = await session.scalar(
        select(func.count())
        .select_from(AuditEntry)
        .where(AuditEntry.action == "retrieval.context.blocked")
        .where(AuditEntry.at >= window_start)
        .where(AuditEntry.at <= window_end)
    ) or 0

    for _ in range(guardrail_count):
        events.append({
            "latency_ms": 0,
            "error": False,
            "cost_usd": 0.0,
            "guardrail_triggered": True,
        })

    return events


async def persist_slo_alerts(
    session: AsyncSession,
    alerts: dict,
    window_start: datetime,
    window_end: datetime,
    created_by: str | None = None,
) -> list[uuid.UUID]:
    """Persist fired SLO alerts to the ``slo_alerts`` table.

    Stores only alert_name, actual, threshold, window_start, window_end, and created_by.
    Never stores message content, prompts, answers, document text, tokens, secrets, or credentials.

    Returns a list of persisted SloAlert ids (one per fired alert).
    """
    ids: list[uuid.UUID] = []
    for alert in alerts.get("alerts", []):
        row = SloAlert(
            alert_name=str(alert["name"]),
            actual=float(alert["actual"]),
            threshold=float(alert["threshold"]),
            window_start=window_start,
            window_end=window_end,
            created_by=created_by,
        )
        session.add(row)
        await session.flush()
        ids.append(row.id)
    await session.commit()
    return ids


async def notify_slo_alerts(
    session: AsyncSession,
    alerts: dict,
    window_start: datetime,
    window_end: datetime,
) -> int:
    """Deliver safe in-app notifications for fired SLO alerts to admin and evaluator users.

    Details contain only alert_name, actual, threshold, and window boundaries —
    never raw prompts, answers, document text, secrets, tokens, or credentials.

    Returns the number of Notification rows created.
    """
    if not alerts.get("any_firing"):
        return 0

    operator_users = list((await session.execute(
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(Role.name.in_(["admin", "evaluator"]))
        .where(User.status == "active")
        .distinct()
    )).scalars().all())

    count = 0
    for user in operator_users:
        for alert in alerts.get("alerts", []):
            session.add(Notification(
                user_id=user.id,
                kind="slo.alert.fired",
                details={
                    "alert_name": str(alert["name"]),
                    "actual": float(alert["actual"]),
                    "threshold": float(alert["threshold"]),
                    "window_start": window_start.isoformat(),
                    "window_end": window_end.isoformat(),
                },
            ))
            count += 1

    return count


# ---------------------------------------------------------------------------
# API routes (FR-O5)
# ---------------------------------------------------------------------------


class SloMetricsIn(BaseModel):
    events: list[dict]
    policy: dict | None = None


class SloWindowIn(BaseModel):
    window_start: datetime
    window_end: datetime
    policy: dict | None = None
    created_by: str | None = None


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


@router.post("/slo-window")
async def slo_window_api(
    body: SloWindowIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """FR-O5: aggregate SLO metrics from DB messages for a time window and persist fired alerts.

    Reads assistant Message rows in the specified time window, computes aggregated SLO metrics,
    evaluates alert firing decisions, and persists any fired alerts with safe metadata only.

    Returns aggregated metrics, alert decisions, event count, window boundaries, and persisted
    alert count. Never returns raw message content, prompts, answers, or secrets.
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

    events = await aggregate_slo_events_from_db(db, body.window_start, body.window_end)
    metrics = compute_slo_metrics(events)
    alerts = check_slo_alerts(metrics, policy)

    persisted_ids: list[uuid.UUID] = []
    if alerts["any_firing"]:
        persisted_ids = await persist_slo_alerts(
            db, alerts, body.window_start, body.window_end, created_by=body.created_by
        )
        await notify_slo_alerts(db, alerts, body.window_start, body.window_end)
        await db.commit()

    return {
        "metrics": metrics,
        "alerts": alerts,
        "event_count": len(events),
        "window_start": body.window_start.isoformat(),
        "window_end": body.window_end.isoformat(),
        "persisted_alert_count": len(persisted_ids),
    }
