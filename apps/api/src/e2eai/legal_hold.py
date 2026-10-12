"""Legal hold for documents and chats, overriding retention (FR-D13).

- Only admins place or release holds.
- A held conversation cannot be deleted (user delete is blocked in chat.py; the retention sweep skips it).
- A held document is never purge-eligible (purge_document already blocks on `legal_hold`; the sweep skips it).
- Audit events store only the hold flag and whether a reason was given, never the reason text,
  titles, or content.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .auth import current_session, require_scope
from .core.errors import AppError
from .db import Conversation, Document, Role, User, UserRole, get_session


async def is_admin(session: AsyncSession, user: User) -> bool:
    role = await session.scalar(select(Role).where(Role.name == "admin"))
    if role is None:
        return False
    return await session.scalar(
        select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id)
    ) is not None


async def _require_admin(session: AsyncSession, user: User) -> None:
    if user.status != "active" or not await is_admin(session, user):
        raise AppError(403, "Not allowed")


async def set_conversation_hold(
    session: AsyncSession, *, actor: User, conversation_id: uuid.UUID, hold: bool, reason: str = ""
) -> None:
    await _require_admin(session, actor)
    conv = await session.get(Conversation, conversation_id)
    if conv is None:
        raise AppError(404, "Conversation not found")
    # Explicit updated_at keeps the conversation's recency: a hold must not reset the retention clock.
    await session.execute(
        update(Conversation).where(Conversation.id == conversation_id)
        .values(legal_hold=hold, updated_at=Conversation.updated_at)
    )
    await audit.record(session, f"user:{actor.id}", "legal_hold.conversation.set",
                       f"conversation:{conversation_id}", {"hold": hold, "reason_given": bool(reason)})
    await session.commit()


async def set_document_hold(
    session: AsyncSession, *, actor: User, document_id: uuid.UUID, hold: bool, reason: str = ""
) -> None:
    await _require_admin(session, actor)
    doc = await session.get(Document, document_id)
    if doc is None or doc.status == "purged":
        raise AppError(404, "Document not found")
    doc.legal_hold = hold
    await audit.record(session, f"user:{actor.id}", "legal_hold.document.set",
                       f"document:{document_id}", {"hold": hold, "reason_given": bool(reason)})
    await session.commit()


async def list_holds(session: AsyncSession) -> dict[str, list[str]]:
    docs = (await session.scalars(select(Document.id).where(Document.legal_hold.is_(True)).order_by(Document.id))).all()
    convs = (await session.scalars(select(Conversation.id).where(Conversation.legal_hold.is_(True)).order_by(Conversation.id))).all()
    return {"documents": [str(d) for d in docs], "conversations": [str(c) for c in convs]}


@dataclass
class _SystemActor:
    id: str = "retention-sweep"


async def _default_purge(session: AsyncSession, document_id: uuid.UUID) -> None:
    from .authz import connect
    from .core.config import get_settings
    from .documents import purge_document

    await purge_document(session, await connect(get_settings(), session), actor=_SystemActor(), document_id=document_id)  # type: ignore[arg-type]


async def retention_sweep(
    session: AsyncSession,
    *,
    chats_days: int = 365,
    trash_days: int = 30,
    dry_run: bool = False,
    purge_document_fn: Callable[[uuid.UUID], Awaitable[None]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Apply retention while skipping anything under legal hold. Returns counts and ids only."""
    if chats_days < 1 or trash_days < 0:
        raise AppError(400, "Invalid retention window")
    current = now or datetime.now(UTC)
    chat_cutoff = current - timedelta(days=chats_days)
    trash_cutoff = current - timedelta(days=trash_days)

    due_chat_ids = list((await session.scalars(
        select(Conversation.id).where(Conversation.updated_at < chat_cutoff, Conversation.legal_hold.is_(False))
    )).all())
    held_chats = await session.scalar(
        select(func.count()).select_from(Conversation)
        .where(Conversation.updated_at < chat_cutoff, Conversation.legal_hold.is_(True))
    ) or 0
    due_doc_ids = list((await session.scalars(
        select(Document.id).where(
            Document.status == "trashed", Document.trashed_at < trash_cutoff, Document.legal_hold.is_(False)
        ).order_by(Document.id)
    )).all())
    held_docs = await session.scalar(
        select(func.count()).select_from(Document)
        .where(Document.status == "trashed", Document.trashed_at < trash_cutoff, Document.legal_hold.is_(True))
    ) or 0

    deleted_chats = 0
    purged_docs = 0
    if not dry_run:
        if due_chat_ids:
            await session.execute(delete(Conversation).where(Conversation.id.in_(due_chat_ids)))
            deleted_chats = len(due_chat_ids)
            await audit.record(session, "system:retention", "retention.chats.delete", "conversations",
                               {"count": deleted_chats})
            await session.commit()
        for document_id in due_doc_ids:
            if purge_document_fn is not None:
                await purge_document_fn(document_id)
            else:
                await _default_purge(session, document_id)
            purged_docs += 1
    return {
        "dry_run": dry_run,
        "chats_due": len(due_chat_ids),
        "chats_deleted": deleted_chats,
        "documents_due": [str(d) for d in due_doc_ids],
        "documents_purged": purged_docs,
        "held_chats_skipped": int(held_chats),
        "held_documents_skipped": int(held_docs),
    }


class HoldIn(BaseModel):
    hold: bool
    reason: str = ""


class SweepIn(BaseModel):
    chats_days: int = 365
    trash_days: int = 30
    dry_run: bool = True


router = APIRouter(prefix="/api/v1/legal-hold", tags=["legal-hold"])


async def _user(db: AsyncSession, sess: dict) -> User:
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None or user.status != "active":
        raise AppError(401, "Not authenticated")
    return user


@router.put("/documents/{document_id}")
async def set_document_hold_api(
    document_id: uuid.UUID, body: HoldIn,
    sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    require_scope(sess, "admin")
    await set_document_hold(db, actor=await _user(db, sess), document_id=document_id, hold=body.hold, reason=body.reason)
    return {"status": "ok", "hold": body.hold}


@router.put("/conversations/{conversation_id}")
async def set_conversation_hold_api(
    conversation_id: uuid.UUID, body: HoldIn,
    sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    require_scope(sess, "admin")
    await set_conversation_hold(db, actor=await _user(db, sess), conversation_id=conversation_id,
                                hold=body.hold, reason=body.reason)
    return {"status": "ok", "hold": body.hold}


@router.get("")
async def list_holds_api(
    sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    require_scope(sess, "admin")
    await _require_admin(db, await _user(db, sess))
    return await list_holds(db)


@router.post("/retention-sweep")
async def retention_sweep_api(
    body: SweepIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Dry-run by default; held chats/documents are always skipped."""
    require_scope(sess, "admin")
    await _require_admin(db, await _user(db, sess))
    return await retention_sweep(db, chats_days=body.chats_days, trash_days=body.trash_days, dry_run=body.dry_run)
