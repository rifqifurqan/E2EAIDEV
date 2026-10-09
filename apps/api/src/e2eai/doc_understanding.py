"""Document-understanding test set (FR-T13).

Deterministic/offline Lab metrics for comparing baseline parsing vs VLM add-on:
table QA, chart QA, figure/diagram QA, OCR character-error-rate (CER), and
safety-warning-included checks for manuals.

Stored results contain only metric numbers, kind labels, and pass/fail flags —
never raw table text, chart values, OCR text, warning text, document snippets,
or answers.
"""

import uuid
from collections import defaultdict
from collections.abc import Sequence

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import current_session, require_scope
from .db import EvalDataset, EvalRun, get_session
from .eval_lab import _current_user, create_dataset


# ---------------------------------------------------------------------------
# Pure metrics
# ---------------------------------------------------------------------------

def _levenshtein(a: str, b: str) -> int:
    """Minimum edit distance (insertions, deletions, substitutions)."""
    if not a:
        return len(b)
    if not b:
        return len(a)
    m, n = len(a), len(b)
    prev = list(range(n + 1))
    for i in range(1, m + 1):
        curr = [i] + [0] * n
        for j in range(1, n + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[n]


def character_error_rate(reference: str, hypothesis: str) -> float:
    """CER = edit_distance / max(len(reference), 1), capped at 1.0."""
    if not reference and not hypothesis:
        return 0.0
    if not reference:
        return 1.0
    dist = _levenshtein(reference, hypothesis)
    return min(round(dist / len(reference), 4), 1.0)


def _score_qa(items: Sequence[dict]) -> dict:
    """Score exact-match QA items (table_qa, chart_qa, figure_qa)."""
    correct = sum(1 for it in items if str(it.get("expected", "")) == str(it.get("actual", "")))
    total = len(items)
    return {
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else 0.0,
    }


def _score_ocr(items: Sequence[dict]) -> dict:
    cers = [character_error_rate(str(it.get("expected", "")), str(it.get("actual", ""))) for it in items]
    total = len(items)
    return {
        "total": total,
        "mean_cer": round(sum(cers) / total, 4) if total else 0.0,
    }


def _score_safety(items: Sequence[dict]) -> dict:
    all_included = 0
    for it in items:
        warnings = it.get("expected_warnings") or []
        text = str(it.get("actual_text", ""))
        if warnings and all(w in text for w in warnings):
            all_included += 1
    total = len(items)
    return {
        "total": total,
        "all_included": all_included,
        "inclusion_rate": round(all_included / total, 4) if total else 0.0,
    }


def score_items(items: Sequence[dict]) -> dict:
    """Score a mixed batch of document-understanding items by kind."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        grouped[it.get("kind", "unknown")].append(it)

    result: dict[str, dict] = {}
    for kind in ("table_qa", "chart_qa", "figure_qa"):
        if kind in grouped:
            result[kind] = _score_qa(grouped[kind])
    if "ocr" in grouped:
        result["ocr"] = _score_ocr(grouped["ocr"])
    if "safety_warning" in grouped:
        result["safety_warning"] = _score_safety(grouped["safety_warning"])
    return result


# ---------------------------------------------------------------------------
# Safe item results (no raw content)
# ---------------------------------------------------------------------------

def _safe_item_result(index: int, item: dict) -> dict:
    """Build a safe item result: metric numbers and labels only."""
    kind = item.get("kind", "unknown")
    entry: dict = {"index": index, "kind": kind}

    if kind in ("table_qa", "chart_qa", "figure_qa"):
        entry["correct"] = str(item.get("expected", "")) == str(item.get("actual", ""))
    elif kind == "ocr":
        entry["cer"] = character_error_rate(
            str(item.get("expected", "")), str(item.get("actual", ""))
        )
    elif kind == "safety_warning":
        warnings = item.get("expected_warnings") or []
        text = str(item.get("actual_text", ""))
        entry["warnings_expected"] = len(warnings)
        entry["all_included"] = bool(warnings and all(w in text for w in warnings))

    return entry


# ---------------------------------------------------------------------------
# DB-backed evaluation
# ---------------------------------------------------------------------------

async def evaluate_doc_understanding(
    session: AsyncSession,
    *,
    name: str,
    items: Sequence[dict],
    created_by: str,
    dataset_id: uuid.UUID | None = None,
) -> EvalRun:
    """Run a document-understanding eval and store a safe EvalRun (FR-T13).

    The dataset stores only kind labels and safe metadata (no raw content).
    """
    metrics = score_items(items)
    metrics["items"] = len(items)

    item_results = [_safe_item_result(i, it) for i, it in enumerate(items)]

    if dataset_id is None:
        safe_dataset_items = [{"kind": it.get("kind", "unknown"), "index": i} for i, it in enumerate(items)]
        ds = await create_dataset(
            session,
            name=name,
            items=safe_dataset_items,
            source="doc_understanding",
            created_by=created_by,
        )
        dataset_id = ds.id

    run = EvalRun(
        dataset_id=dataset_id,
        adapter="doc-understanding.local",
        status="completed",
        metrics=metrics,
        item_results=item_results,
        created_by=created_by,
    )
    session.add(run)
    await session.commit()
    return run


# ---------------------------------------------------------------------------
# FastAPI route
# ---------------------------------------------------------------------------

class DocUnderstandingIn(BaseModel):
    name: str = "doc-understanding"
    dataset_id: uuid.UUID | None = None
    items: list[dict]


router = APIRouter(prefix="/api/v1/evals", tags=["evals"])


@router.post("/doc-understanding")
async def run_doc_understanding_api(
    body: DocUnderstandingIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """FR-T13: run document-understanding metrics and store a safe EvalRun."""
    from .auth import redis_client
    from .quotas import enforce_request_quota, get_effective_policy

    require_scope(sess, "evals")
    user = await _current_user(db, sess)

    policy = await get_effective_policy(db, user=user)
    await enforce_request_quota(
        redis_client(), user_id=sess["user_id"],
        endpoint="evals.doc_understanding", policy=policy,
    )

    eval_run = await evaluate_doc_understanding(
        db,
        name=body.name,
        items=[it.copy() for it in body.items],
        created_by=f"user:{user.id}",
        dataset_id=body.dataset_id,
    )
    return {
        "id": str(eval_run.id),
        "adapter": eval_run.adapter,
        "metrics": eval_run.metrics,
        "item_results": eval_run.item_results,
    }
