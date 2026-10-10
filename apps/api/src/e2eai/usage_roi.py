"""Usage and ROI analytics (FR-O7).

Computes active users, questions per division, answer rate, deflection count/rate,
top unanswered topics, and estimated time saved from usage event dictionaries.
Outputs are safe: only aggregate metrics, IDs/numbers, and topic strings — never
raw prompts, answers, question text, document text, secrets, tokens, or credentials.
"""

from collections import defaultdict
from collections.abc import Sequence

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import current_session, require_scope
from .core.errors import AppError
from .db import get_session

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
