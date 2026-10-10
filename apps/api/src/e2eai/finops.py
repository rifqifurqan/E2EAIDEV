"""FinOps: spend per user/team/division/bot, budgets, alerts, chargeback reports (FR-O6).

Computes spend aggregation by dimension, evaluates budget threshold alert decisions, and
builds safe chargeback reports from already-recorded cost/token metadata events. Outputs
are safe: only aggregated spend, budget metadata, and alert decisions — never raw prompts,
answers, document text, restricted titles/snippets, secrets, tokens, or credentials.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import current_session, require_scope
from .core.errors import AppError
from .db import Conversation, Message, TeamMember, User, get_session

# Conservative token cost estimate; real cost depends on the LiteLLM model/provider.
# ponytail: replace with persisted per-model LiteLLM cost metadata when available.
_TOKEN_COST_USD: float = 2e-6  # 0.000002 USD/token ≈ $2/1M tokens


@dataclass(frozen=True)
class BudgetPolicy:
    """Configurable budget thresholds per dimension (FR-O6).

    Each field sets the maximum acceptable spend in USD; exceeding it fires an alert.
    """

    user_budget_usd: float = 10.0
    team_budget_usd: float = 50.0
    division_budget_usd: float = 200.0
    bot_budget_usd: float = 100.0


def aggregate_spend(events: Sequence[dict]) -> dict:
    """Aggregate spend from cost/token metadata events by user, team, division, and bot.

    Each event dict should have at minimum:
        user_id (str), team_id (str), division_id (str), bot_id (str),
        cost_usd (float), tokens (int).

    Returns aggregated spend only — no raw content, prompts, answers, or secrets.
    """
    n = len(events)
    if n == 0:
        return {
            "total_events": 0,
            "total_cost_usd": 0.0,
            "by_user": [],
            "by_team": [],
            "by_division": [],
            "by_bot": [],
        }

    dimensions = {
        "user": "user_id",
        "team": "team_id",
        "division": "division_id",
        "bot": "bot_id",
    }

    results: dict[str, list[dict]] = {}

    for dim_name, dim_key in dimensions.items():
        cost_agg: dict[str, float] = defaultdict(float)
        token_agg: dict[str, int] = defaultdict(int)
        count_agg: dict[str, int] = defaultdict(int)

        for e in events:
            dim_id = str(e.get(dim_key, "unknown"))
            cost_agg[dim_id] += float(e.get("cost_usd", 0))
            token_agg[dim_id] += int(e.get("tokens", 0))
            count_agg[dim_id] += 1

        results[f"by_{dim_name}"] = [
            {
                "id": dim_id,
                "cost_usd": round(cost, 6),
                "tokens": token_agg[dim_id],
                "event_count": count_agg[dim_id],
            }
            for dim_id, cost in sorted(cost_agg.items())
        ]

    total_cost = sum(float(e.get("cost_usd", 0)) for e in events)

    return {
        "total_events": n,
        "total_cost_usd": round(total_cost, 6),
        **results,
    }


def check_budget_alerts(spend: dict, policy: BudgetPolicy) -> dict:
    """Evaluate budget alert firing decisions against thresholds per dimension.

    Returns a dict with ``any_firing`` (bool), ``total_checked`` (int), and ``alerts``
    (list of fired alerts with dimension, id, actual, threshold).
    Output is safe: only dimension names and numbers.
    """
    budget_map = {
        "user": policy.user_budget_usd,
        "team": policy.team_budget_usd,
        "division": policy.division_budget_usd,
        "bot": policy.bot_budget_usd,
    }

    fired = []
    total_checked = 0

    for dim_name, threshold in budget_map.items():
        entries = spend.get(f"by_{dim_name}", [])
        for entry in entries:
            total_checked += 1
            if entry["cost_usd"] > threshold:
                fired.append({
                    "dimension": dim_name,
                    "id": entry["id"],
                    "actual": entry["cost_usd"],
                    "threshold": threshold,
                })

    return {
        "any_firing": len(fired) > 0,
        "total_checked": total_checked,
        "alerts": fired,
    }


def build_chargeback_report(spend: dict) -> dict:
    """Build a safe chargeback report from aggregated spend data.

    Returns only dimension-level aggregates with id, cost_usd, and event_count.
    Never includes raw prompts, answers, document text, secrets, tokens, or credentials.
    """
    report: dict = {
        "total_cost_usd": spend.get("total_cost_usd", 0.0),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    for dim in ("by_user", "by_team", "by_division", "by_bot"):
        report[dim] = [
            {
                "id": entry["id"],
                "cost_usd": entry["cost_usd"],
                "event_count": entry["event_count"],
            }
            for entry in spend.get(dim, [])
        ]

    return report


# ---------------------------------------------------------------------------
# DB-backed spend aggregation (FR-O6)
# ---------------------------------------------------------------------------


async def aggregate_spend_events_from_db(
    session: AsyncSession,
    window_start: datetime,
    window_end: datetime,
) -> list[dict]:
    """Read safe spend metadata from persisted assistant messages in a time window.

    Joins ``Message`` -> ``Conversation`` -> ``User`` plus ``TeamMember`` to emit event
    dicts compatible with ``aggregate_spend``. Only IDs, token counts, and estimated
    cost are returned. Message content, role, model name, prompts, answers, document
    text, snippets, credentials, tokens-as-secrets, and API keys are never selected or
    included in the returned payload.
    """
    rows = (
        await session.execute(
            select(
                Conversation.user_id,
                Conversation.bot_id,
                User.division_id,
                TeamMember.team_id,
                Message.tokens,
            )
            .select_from(Message)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .join(User, User.id == Conversation.user_id)
            .outerjoin(TeamMember, TeamMember.user_id == User.id)
            .where(Message.role == "assistant")
            .where(Message.created_at >= window_start)
            .where(Message.created_at <= window_end)
        )
    ).all()

    events: list[dict] = []
    for row in rows:
        token_count = int(row.tokens or 0)
        events.append({
            "user_id": str(row.user_id),
            "team_id": str(row.team_id) if row.team_id is not None else "unknown",
            "division_id": str(row.division_id) if row.division_id is not None else "unknown",
            "bot_id": str(row.bot_id) if row.bot_id is not None else "unknown",
            "cost_usd": round(token_count * _TOKEN_COST_USD, 6),
            "tokens": token_count,
        })

    return events


async def get_finops_window_report(
    session: AsyncSession,
    window_start: datetime,
    window_end: datetime,
    policy: BudgetPolicy | None = None,
) -> dict:
    """Build a safe DB-backed FinOps report for a time window.

    Returns window metadata, aggregate spend, budget alert decisions, and chargeback
    report data. All fields are aggregate IDs/numbers only; no raw message content,
    model names, prompts, answers, snippets, secrets, credentials, or API keys.
    """
    if policy is None:
        policy = BudgetPolicy()

    events = await aggregate_spend_events_from_db(session, window_start, window_end)
    spend = aggregate_spend(events)
    alerts = check_budget_alerts(spend, policy)
    return {
        "window": {
            "start": window_start.isoformat(),
            "end": window_end.isoformat(),
        },
        "event_count": len(events),
        "spend": spend,
        "alerts": alerts,
        "report": build_chargeback_report(spend),
    }


# ---------------------------------------------------------------------------
# API routes (FR-O6)
# ---------------------------------------------------------------------------


class FinopsSpendIn(BaseModel):
    events: list[dict]
    policy: dict | None = None


router = APIRouter(prefix="/api/v1/operate", tags=["operate"])


@router.post("/finops-spend")
async def finops_spend_api(
    body: FinopsSpendIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """FR-O6: compute spend aggregation by user/team/division/bot and evaluate budget alerts.

    Accepts cost/token metadata events and an optional budget policy override.
    Returns aggregated spend and alert metadata only — never raw prompts, answers, or secrets.
    """
    require_scope(sess, "evals")

    policy = BudgetPolicy()
    if body.policy:
        policy = BudgetPolicy(
            user_budget_usd=float(body.policy.get("user_budget_usd", policy.user_budget_usd)),
            team_budget_usd=float(body.policy.get("team_budget_usd", policy.team_budget_usd)),
            division_budget_usd=float(body.policy.get("division_budget_usd", policy.division_budget_usd)),
            bot_budget_usd=float(body.policy.get("bot_budget_usd", policy.bot_budget_usd)),
        )

    if not body.events:
        raise AppError(400, "Events list is required")

    spend = aggregate_spend(body.events)
    alerts = check_budget_alerts(spend, policy)

    return {"spend": spend, "alerts": alerts}


@router.post("/finops-chargeback")
async def finops_chargeback_api(
    body: FinopsSpendIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """FR-O6: build a safe chargeback report from spend events.

    Returns only aggregated spend per user/team/division/bot with cost and event count.
    Never returns raw prompts, answers, document text, secrets, or credentials.
    """
    require_scope(sess, "evals")

    if not body.events:
        raise AppError(400, "Events list is required")

    spend = aggregate_spend(body.events)
    report = build_chargeback_report(spend)
    alerts = check_budget_alerts(spend, BudgetPolicy())

    return {"report": report, "alerts": alerts}


@router.get("/finops-window")
async def finops_window_api(
    window_hours: int = 24,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """FR-O6: DB-backed spend aggregation for a rolling time window.

    Reads persisted assistant message metadata, aggregates spend by user/team/division/bot,
    evaluates budget thresholds, and returns a safe chargeback report. The response never
    includes raw prompts, answers, document text, model names, secrets, or credentials.
    """
    require_scope(sess, "evals")

    now = datetime.now(timezone.utc)
    hours = max(1, min(window_hours, 720))
    window_start = now - timedelta(hours=hours)
    return await get_finops_window_report(db, window_start, now)

