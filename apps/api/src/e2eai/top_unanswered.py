"""Top unanswered questions report for knowledge owners (FR-I2).

Aggregates unanswered topic buckets from usage events and returns a
knowledge-gap report: which topic areas lack documentation, ranked by
frequency and breadth (number of divisions affected).

Outputs safe aggregate metrics only — never raw prompts, question text,
answers, document text, titles, snippets, secrets, tokens, or credentials.
"""

from collections import defaultdict
from collections.abc import Sequence

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import current_session, require_scope
from .core.errors import AppError
from .db import get_session
from .usage_roi import _safe_topic_label  # reuse existing redaction guard

_MAX_GAPS = 20  # knowledge-gap report cap


def compute_top_unanswered_report(events: Sequence[dict]) -> dict:
    """Compute FR-I2 top unanswered questions knowledge-gap report.

    Each event dict may have:
        user_id (str), division_id (str), answered (bool), topic (str).
        question/answer/content fields are present in events but never included
        in the output — only aggregate metrics, IDs, and safe topic labels.

    Returns:
        total_unanswered: count of events where answered is False/missing.
        unique_topics: number of distinct unanswered topic buckets.
        top_unanswered_gaps: list of gap entries (up to _MAX_GAPS), sorted
            by count descending. Each entry has:
                topic (str): safe aggregate topic bucket label.
                count (int): how many times this topic was asked and unanswered.
                division_ids (list[str]): sorted list of distinct division IDs
                    that asked unanswered questions in this topic area.
                division_count (int): len(division_ids).
    """
    unanswered = [e for e in events if not e.get("answered", False)]

    if not unanswered:
        return {
            "total_unanswered": 0,
            "unique_topics": 0,
            "top_unanswered_gaps": [],
        }

    topic_counts: dict[str, int] = defaultdict(int)
    topic_divisions: dict[str, set[str]] = defaultdict(set)

    for e in unanswered:
        topic = _safe_topic_label(e.get("topic", "unknown"))
        div_id = str(e.get("division_id", "unknown"))
        topic_counts[topic] += 1
        topic_divisions[topic].add(div_id)

    sorted_gaps = sorted(
        topic_counts.items(),
        key=lambda x: (-x[1], -len(topic_divisions[x[0]]), x[0]),
    )[:_MAX_GAPS]

    return {
        "total_unanswered": len(unanswered),
        "unique_topics": len(topic_counts),
        "top_unanswered_gaps": [
            {
                "topic": topic,
                "count": count,
                "division_ids": sorted(topic_divisions[topic]),
                "division_count": len(topic_divisions[topic]),
            }
            for topic, count in sorted_gaps
        ],
    }


# ---------------------------------------------------------------------------
# API route (FR-I2)
# ---------------------------------------------------------------------------


class TopUnansweredIn(BaseModel):
    events: list[dict]


router = APIRouter(prefix="/api/v1/improve", tags=["improve"])


@router.post("/top-unanswered")
async def top_unanswered_api(
    body: TopUnansweredIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """FR-I2: top unanswered questions report for knowledge owners.

    Accepts usage event records and returns an aggregate knowledge-gap report:
    which topic areas are most frequently unanswered, ranked by count and
    breadth across divisions. Helps knowledge owners identify missing documents.

    Never returns raw question text, prompts, answers, document text, titles,
    snippets, secrets, tokens, or credentials.
    """
    require_scope(sess, "evals")

    if not body.events:
        raise AppError(400, "Events list is required")

    return {"report": compute_top_unanswered_report(body.events)}
