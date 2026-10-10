"""Usage and ROI analytics (FR-O7).

Computes active users, questions per division, answer rate, deflection count/rate,
top unanswered topics, and estimated time saved from usage event dictionaries.
Outputs are safe: only aggregate metrics, IDs/numbers, and topic strings — never
raw prompts, answers, question text, document text, secrets, tokens, or credentials.
"""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import current_session, require_scope
from .core.errors import AppError
from .db import Conversation, Message, MessageCitation, MessageFeedback, User, get_session

_FORBIDDEN_TOPIC_MARKERS = (
    "secret",
    "password",
    "credential",
    "bearer",
    "api key",
    "api_key",
    "token",
    "production",
)


def _safe_topic_label(topic: object) -> str:
    """Return a safe aggregate topic label, redacting likely secret-bearing labels.

    Topic labels are allowed in FR-O7 aggregate output, but upstream classifiers or callers
    might accidentally pass raw user text. If a label contains secret/credential markers,
    collapse it to a generic bucket rather than leaking the text.
    """
    label = str(topic or "unknown").strip() or "unknown"
    lowered = label.lower()
    if any(marker in lowered for marker in _FORBIDDEN_TOPIC_MARKERS):
        return "redacted"
    return label


def compute_usage_roi_report(events: Sequence[dict]) -> dict:
    """Compute FR-O7 usage and ROI metrics from usage event dicts.

    Each event dict may have:
        user_id (str), division_id (str), question (str — ignored in output),
        answered (bool), deflected (bool), topic (str), time_saved_minutes (int|float).

    Returns aggregate metrics only — no raw question text, answers, prompts,
    document text, secrets, tokens, or credentials.
    """
    n = len(events)
    if n == 0:
        return {
            "active_users": 0,
            "total_questions": 0,
            "questions_per_division": [],
            "answer_rate": 0.0,
            "deflection_count": 0,
            "deflection_rate": 0.0,
            "top_unanswered_topics": [],
            "estimated_time_saved_minutes": 0,
        }

    user_ids: set[str] = set()
    div_counts: dict[str, int] = defaultdict(int)
    answered_count = 0
    deflected_count = 0
    unanswered_topics: dict[str, int] = defaultdict(int)
    total_time_saved = 0

    for e in events:
        user_ids.add(str(e.get("user_id", "unknown")))

        div_id = str(e.get("division_id", "unknown"))
        div_counts[div_id] += 1

        if e.get("answered", False):
            answered_count += 1
        else:
            topic = _safe_topic_label(e.get("topic", "unknown"))
            unanswered_topics[topic] += 1

        if e.get("deflected", False):
            deflected_count += 1

        total_time_saved += int(e.get("time_saved_minutes", 0))

    # Sort unanswered topics by frequency descending, cap at 10
    sorted_unanswered = sorted(unanswered_topics.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "active_users": len(user_ids),
        "total_questions": n,
        "questions_per_division": [
            {"division_id": div_id, "count": count}
            for div_id, count in sorted(div_counts.items())
        ],
        "answer_rate": round(answered_count / n, 4),
        "deflection_count": deflected_count,
        "deflection_rate": round(deflected_count / n, 4),
        "top_unanswered_topics": [
            {"topic": topic, "count": count}
            for topic, count in sorted_unanswered
        ],
        "estimated_time_saved_minutes": total_time_saved,
    }


# ---------------------------------------------------------------------------
# API routes (FR-O7)
# ---------------------------------------------------------------------------


class UsageRoiIn(BaseModel):
    events: list[dict]


router = APIRouter(prefix="/api/v1/operate", tags=["operate"])


@router.post("/usage-roi")
async def usage_roi_api(
    body: UsageRoiIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """FR-O7: compute usage and ROI analytics from usage events.

    Accepts usage event records and returns aggregate metrics only — active users,
    questions per division, answer rate, deflection count/rate, top unanswered topics,
    and estimated time saved. Never returns raw question text, prompts, answers,
    document text, secrets, tokens, or credentials.
    """
    require_scope(sess, "evals")

    if not body.events:
        raise AppError(400, "Events list is required")

    return {"report": compute_usage_roi_report(body.events)}


# ---------------------------------------------------------------------------
# DB-backed usage/ROI aggregation (FR-O7)
# ---------------------------------------------------------------------------

# Conservative estimate: minutes saved per answered question (typical manual search time).
_DEFAULT_TIME_SAVED_MINUTES: int = 5


async def aggregate_usage_events_from_db(
    session: AsyncSession,
    window_start: datetime,
    window_end: datetime,
) -> list[dict]:
    """Read safe usage metadata from persisted user messages in a time window.

    Joins ``Message`` (role='user') → ``Conversation`` → ``User`` to extract user_id and
    division_id. For each user message, finds the next assistant message in the same
    conversation and infers:
      - **answered**: True when a subsequent assistant Message exists with stop_reason not
        in ('error', 'no_answer') and either has at least one ``MessageCitation`` or
        non-empty content.
      - **deflected**: True when the paired assistant has at least one ``MessageCitation``
        or positive ``MessageFeedback`` (rating='up').
      - **topic**: safe constant 'unanswered' or 'answered' — never raw question text.

    Returns a list of safe event dicts compatible with ``compute_usage_roi_report``.
    Message content, role, model name, prompts, answers, document text, snippets,
    credentials, and API keys are never selected or included in the returned payload.
    """
    # Step 1: user messages in window with user/division metadata
    user_msg_rows = (
        await session.execute(
            select(
                Message.id,
                Message.conversation_id,
                Conversation.user_id,
                User.division_id,
                Message.created_at,
            )
            .select_from(Message)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .join(User, User.id == Conversation.user_id)
            .where(Message.role == "user")
            .where(Message.created_at >= window_start)
            .where(Message.created_at <= window_end)
            .order_by(Message.conversation_id, Message.created_at)
        )
    ).all()

    if not user_msg_rows:
        return []

    # Step 2: assistant messages in those conversations — safe columns only
    conv_ids = list({r.conversation_id for r in user_msg_rows})
    asst_rows = (
        await session.execute(
            select(
                Message.id,
                Message.conversation_id,
                Message.created_at,
                Message.stop_reason,
                (func.coalesce(func.length(Message.content), 0) > 0).label("has_content"),
            )
            .where(Message.role == "assistant")
            .where(Message.conversation_id.in_(conv_ids))
            .order_by(Message.conversation_id, Message.created_at)
        )
    ).all()

    asst_by_conv: dict[uuid.UUID, list] = defaultdict(list)
    for ar in asst_rows:
        asst_by_conv[ar.conversation_id].append(ar)

    # Step 3: citation counts per assistant message
    asst_ids = [ar.id for ar in asst_rows]
    citation_counts: dict[uuid.UUID, int] = {}
    if asst_ids:
        cite_rows = (
            await session.execute(
                select(MessageCitation.message_id, func.count())
                .where(MessageCitation.message_id.in_(asst_ids))
                .group_by(MessageCitation.message_id)
            )
        ).all()
        citation_counts = {r[0]: r[1] for r in cite_rows}

    # Step 4: positive feedback message IDs
    positive_fb: set[uuid.UUID] = set()
    if asst_ids:
        fb_rows = (
            await session.execute(
                select(MessageFeedback.message_id)
                .where(MessageFeedback.message_id.in_(asst_ids))
                .where(MessageFeedback.rating == "up")
            )
        ).all()
        positive_fb = {r[0] for r in fb_rows}

    # Step 5: pair each user message with its next assistant reply and build events
    events: list[dict] = []
    for um in user_msg_rows:
        paired = None
        user_order = (um.created_at, str(um.id))
        for am in asst_by_conv.get(um.conversation_id, []):
            # PostgreSQL now() is transaction-stable, so rapid test inserts can share
            # the same created_at. UUIDv7 ids preserve insertion order for this slice.
            if (am.created_at, str(am.id)) > user_order:
                paired = am
                break

        answered = False
        deflected = False

        if paired is not None:
            bad_stop = paired.stop_reason in ("error", "no_answer")
            has_citations = citation_counts.get(paired.id, 0) > 0
            has_content = bool(paired.has_content)

            if not bad_stop and (has_citations or has_content):
                answered = True

            if has_citations or paired.id in positive_fb:
                deflected = True

        events.append({
            "user_id": str(um.user_id),
            "division_id": str(um.division_id) if um.division_id else "unknown",
            "answered": answered,
            "deflected": deflected,
            "topic": "unanswered" if not answered else "answered",
            "time_saved_minutes": _DEFAULT_TIME_SAVED_MINUTES if answered else 0,
        })

    return events


async def get_usage_roi_dashboard(
    session: AsyncSession,
    window_start: datetime,
    window_end: datetime,
) -> dict:
    """Build the Usage/ROI dashboard summary for a rolling time window.

    Returns window metadata, safe aggregate report (active users, questions per division,
    answer rate, deflection, unanswered topics, time saved), and event count.
    Never returns raw message content, prompts, answers, model names, document text,
    snippets, tokens, credentials, or titles.
    """
    events = await aggregate_usage_events_from_db(session, window_start, window_end)
    report = compute_usage_roi_report(events)
    return {
        "window": {
            "start": window_start.isoformat(),
            "end": window_end.isoformat(),
        },
        "event_count": len(events),
        "report": report,
    }


@router.get("/usage-roi-dashboard")
async def usage_roi_dashboard_api(
    window_hours: int = 24,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """FR-O7: Usage and ROI dashboard — DB-backed rolling-window aggregate of active users,
    questions per division, answer rate, deflection, unanswered topics, and time saved.

    Safe read-only view for operators. Returns aggregated numeric metrics only.
    Never returns raw prompts, answers, model names, document text, snippets,
    tokens, credentials, or titles.
    """
    require_scope(sess, "evals")

    now = datetime.now(timezone.utc)
    hours = max(1, min(window_hours, 720))
    window_start = now - timedelta(hours=hours)
    return await get_usage_roi_dashboard(db, window_start, now)
