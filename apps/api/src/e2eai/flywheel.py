"""Data flywheel: flagged answers -> triage queue -> eval/fine-tune dataset -> re-eval -> release (FR-I1).

Deterministic/offline. Sources: thumbs-down feedback, low online score, reviewer flag. The queue keeps
only PII-masked question/correction text, ids, and labels (the assistant answer is never stored).
Everything except the user-facing feedback write is admin-only and audited with ids/labels only.
Accepted items with a correction become dataset items (gold split for `eval`, fine_tuning split for
`finetune`) that the existing eval lab (FR-D11 annotations) and re-evaluation flow can consume.
"""

from __future__ import annotations

import uuid
from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .auth import current_session, require_scope
from .core.errors import AppError
from .db import EvalDataset, EvalRun, FlywheelItem, Message, MessageFeedback, User, get_session
from .eval_lab import create_dataset
from .incidents import redact
from .legal_hold import is_admin
from .pii import mask_text

SOURCES = ("thumbs_down", "low_online_score", "reviewer_flag")
TARGETS = ("eval", "finetune")
MAX_TEXT = 4000


async def _require_admin(session: AsyncSession, actor: User) -> None:
    if actor.status != "active" or not await is_admin(session, actor):
        raise AppError(403, "Not allowed")


def _mask(text: str | None, limit: int = MAX_TEXT) -> str:
    return redact(mask_text((text or "").strip()), limit)


def summarize(item: FlywheelItem) -> dict[str, Any]:
    return {
        "id": str(item.id), "source": item.source, "status": item.status, "trace_id": item.trace_id,
        "question": item.question_masked, "correction": item.correction_masked, "reason": item.reason,
        "target": item.target, "dataset_id": str(item.dataset_id) if item.dataset_id else None,
        "eval_run_id": str(item.eval_run_id) if item.eval_run_id else None, "release_ref": item.release_ref,
    }


async def _get(session: AsyncSession, item_id: uuid.UUID) -> FlywheelItem:
    item = await session.get(FlywheelItem, item_id)
    if item is None:
        raise AppError(404, "Flywheel item not found")
    return item


async def collect_from_feedback(session: AsyncSession, *, actor: User, limit: int = 500) -> int:
    """Queue every thumbs-down answer not yet queued. Idempotent (one item per message)."""
    await _require_admin(session, actor)
    queued_ids = set((await session.scalars(select(FlywheelItem.message_id).where(FlywheelItem.message_id.is_not(None)))).all())
    rows = (
        await session.execute(
            select(MessageFeedback, Message).join(Message, Message.id == MessageFeedback.message_id)
            .where(MessageFeedback.rating == "down").order_by(MessageFeedback.created_at).limit(limit)
        )
    ).all()
    created = 0
    for feedback, answer in rows:
        if answer.id in queued_ids:
            continue
        question = await session.scalar(
            select(Message.content)
            .where(Message.conversation_id == answer.conversation_id, Message.role == "user", Message.id < answer.id)
            .order_by(Message.id.desc()).limit(1)
        )
        session.add(FlywheelItem(
            source="thumbs_down", message_id=answer.id, trace_id=feedback.trace_id,
            question_masked=_mask(question), correction_masked=_mask(feedback.correction_masked) or None,
        ))
        created += 1
    if created:
        await audit.record(session, f"user:{actor.id}", "flywheel.collect", "flywheel", {"created": created})
    await session.commit()
    return created


async def flag_answer(
    session: AsyncSession,
    *,
    actor: User,
    source: str,
    question: str,
    correction: str | None = None,
    trace_id: str | None = None,
    reason: str | None = None,
) -> FlywheelItem:
    await _require_admin(session, actor)
    if source not in SOURCES:
        raise AppError(400, "Invalid source")
    if not question or not question.strip():
        raise AppError(400, "Question is required")
    item = FlywheelItem(
        source=source, trace_id=(trace_id or None) and trace_id[:120], question_masked=_mask(question),
        correction_masked=_mask(correction) or None, reason=redact(reason, 300) or None,
    )
    session.add(item)
    await session.flush()
    await audit.record(session, f"user:{actor.id}", "flywheel.flag", f"flywheel:{item.id}", {"source": source})
    await session.commit()
    return item


async def triage_item(
    session: AsyncSession, *, actor: User, item_id: uuid.UUID, decision: str, target: str | None = None
) -> FlywheelItem:
    await _require_admin(session, actor)
    if decision not in ("accept", "dismiss"):
        raise AppError(400, "Decision must be accept or dismiss")
    item = await _get(session, item_id)
    if item.status != "queued":
        raise AppError(409, "Item was already triaged")
    if decision == "accept":
        if target not in TARGETS:
            raise AppError(400, "Target must be eval or finetune")
        if not item.correction_masked:
            raise AppError(400, "A correction (expected answer) is required to accept an item")
        item.status, item.target = "accepted", target
    else:
        item.status, item.target = "dismissed", None
    item.triaged_by = str(actor.id)
    await audit.record(
        session, f"user:{actor.id}", "flywheel.triage", f"flywheel:{item.id}", {"decision": decision, "target": item.target}
    )
    await session.commit()
    return item


async def export_to_dataset(session: AsyncSession, *, actor: User, target: str, name: str) -> EvalDataset:
    """Turn accepted items for `target` into a new versioned dataset (gold or fine_tuning split)."""
    await _require_admin(session, actor)
    if target not in TARGETS:
        raise AppError(400, "Target must be eval or finetune")
    items = (
        await session.scalars(
            select(FlywheelItem).where(FlywheelItem.status == "accepted", FlywheelItem.target == target)
            .order_by(FlywheelItem.created_at, FlywheelItem.id)
        )
    ).all()
    if not items:
        raise AppError(409, "No accepted items to export")
    split = "gold" if target == "eval" else "fine_tuning"
    rows = [
        {
            "item_id": f"flywheel-{i.id}", "question": i.question_masked, "expected_answer": i.correction_masked,
            "annotation": {"labels": [f"flywheel.{i.source}"], "splits": [split], "quality": "accepted", "reviewer_id": i.triaged_by},
        }
        for i in items
    ]
    ds = await create_dataset(session, name=name, items=rows, source="flywheel", created_by=f"user:{actor.id}")
    for i in items:
        i.status, i.dataset_id = "exported", ds.id
    await audit.record(
        session, f"user:{actor.id}", "flywheel.export", f"dataset:{ds.id}", {"target": target, "count": len(items)}
    )
    await session.commit()
    return ds


async def link_reeval(session: AsyncSession, *, actor: User, item_id: uuid.UUID, run_id: uuid.UUID) -> FlywheelItem:
    await _require_admin(session, actor)
    item = await _get(session, item_id)
    if item.status != "exported":
        raise AppError(409, "Item must be exported before re-evaluation")
    if await session.get(EvalRun, run_id) is None:
        raise AppError(404, "Eval run not found")
    item.eval_run_id, item.status = run_id, "reevaluated"
    await audit.record(session, f"user:{actor.id}", "flywheel.reeval", f"flywheel:{item.id}", {"run_id": str(run_id)})
    await session.commit()
    return item


async def link_release(session: AsyncSession, *, actor: User, item_id: uuid.UUID, release_ref: str) -> FlywheelItem:
    await _require_admin(session, actor)
    ref = redact(release_ref, 200)
    if not ref:
        raise AppError(400, "Release reference is required")
    item = await _get(session, item_id)
    if item.status != "reevaluated":
        raise AppError(409, "Item must be re-evaluated before release")
    item.release_ref, item.status = ref, "released"
    await audit.record(session, f"user:{actor.id}", "flywheel.release", f"flywheel:{item.id}", {"release_ref": ref})
    await session.commit()
    return item


async def queue_summary(session: AsyncSession, *, actor: User, status: str | None = None) -> dict[str, Any]:
    await _require_admin(session, actor)
    items = (await session.scalars(select(FlywheelItem).order_by(FlywheelItem.created_at).limit(1000))).all()
    by_status = Counter(i.status for i in items)
    by_source = Counter(i.source for i in items)
    return {
        "by_status": dict(sorted(by_status.items())), "by_source": dict(sorted(by_source.items())),
        "items": [summarize(i) for i in items if status is None or i.status == status][:200],
    }


class FlagIn(BaseModel):
    source: str = "reviewer_flag"
    question: str
    correction: str | None = None
    trace_id: str | None = None
    reason: str | None = None


class TriageIn(BaseModel):
    decision: str
    target: str | None = None


class ExportIn(BaseModel):
    target: str
    name: str


class ReevalIn(BaseModel):
    run_id: uuid.UUID


class ReleaseIn(BaseModel):
    release_ref: str


router = APIRouter(prefix="/api/v1/improve/flywheel", tags=["improve"])


async def _user(db: AsyncSession, sess: dict) -> User:
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None or user.status != "active":
        raise AppError(401, "Not authenticated")
    return user


@router.get("")
async def queue_api(
    status: str | None = None, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    require_scope(sess, "admin")
    return await queue_summary(db, actor=await _user(db, sess), status=status)


@router.post("/collect")
async def collect_api(sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_scope(sess, "admin")
    return {"created": await collect_from_feedback(db, actor=await _user(db, sess))}


@router.post("/flag")
async def flag_api(
    body: FlagIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    require_scope(sess, "admin")
    item = await flag_answer(
        db, actor=await _user(db, sess), source=body.source, question=body.question,
        correction=body.correction, trace_id=body.trace_id, reason=body.reason,
    )
    return summarize(item)


@router.post("/export")
async def export_api(
    body: ExportIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    require_scope(sess, "admin")
    ds = await export_to_dataset(db, actor=await _user(db, sess), target=body.target, name=body.name)
    return {"dataset_id": str(ds.id), "name": ds.name, "version": ds.version, "items": len(ds.items)}


@router.post("/{item_id}/triage")
async def triage_api(
    item_id: uuid.UUID, body: TriageIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    require_scope(sess, "admin")
    return summarize(await triage_item(db, actor=await _user(db, sess), item_id=item_id, decision=body.decision, target=body.target))


@router.post("/{item_id}/reeval")
async def reeval_api(
    item_id: uuid.UUID, body: ReevalIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    require_scope(sess, "admin")
    return summarize(await link_reeval(db, actor=await _user(db, sess), item_id=item_id, run_id=body.run_id))


@router.post("/{item_id}/release")
async def release_api(
    item_id: uuid.UUID, body: ReleaseIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    require_scope(sess, "admin")
    return summarize(await link_release(db, actor=await _user(db, sess), item_id=item_id, release_ref=body.release_ref))
