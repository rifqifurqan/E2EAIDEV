"""Data-subject requests: export or erase a person's data (NFR-10, UU PDP / GDPR-ready).

Admin-only. Export returns the person's own profile, conversations + messages, memories and notifications; it never
includes credentials, hashes, API-key material, or anything belonging to other people. Erasure requires the user to be
offboarded (disabled, FR-F18), refuses while any of their chats or owned documents is under legal hold (FR-D13), deletes
their content and credentials, and pseudonymises the profile row. The append-only audit log is retained (NFR-11); audit
entries written here carry counts and ids only.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import delete, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .auth import current_session, require_scope
from .core.errors import AppError
from .core.pagination import clamp_limit, decode_cursor, make_page
from .db import (
    AccessRequest,
    ApiKey,
    Conversation,
    DataSubjectRequest,
    Document,
    LocalCredential,
    Message,
    Notification,
    User,
    UserMemory,
    UserMemorySetting,
    get_session,
)
from .legal_hold import is_admin


def _iso(value) -> str | None:
    return value.isoformat() if value else None


async def _require_admin(session: AsyncSession, admin: User) -> None:
    if admin.status != "active" or not await is_admin(session, admin):
        raise AppError(403, "Not allowed")


async def _subject(session: AsyncSession, subject_id: uuid.UUID) -> User:
    subject = await session.get(User, subject_id)
    if subject is None:
        raise AppError(404, "User not found")
    return subject


DSR_KINDS = ("export", "erase")
DSR_RESPONSE_DAYS = 30  # response deadline recorded on every request (UU PDP / GDPR-ready)


def _request_view(req: DataSubjectRequest, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    return {
        "id": str(req.id), "subject_id": str(req.subject_id) if req.subject_id else None, "kind": req.kind,
        "status": req.status, "received_at": _iso(req.received_at), "due_at": _iso(req.due_at),
        "completed_at": _iso(req.completed_at),
        "overdue": req.status == "open" and req.due_at < now,
    }


async def open_request(
    session: AsyncSession, *, admin: User, subject_id: uuid.UUID, kind: str, received_at: datetime | None = None,
) -> dict[str, Any]:
    """Record a data-subject request with its deadline. The ledger keeps ids and labels, never personal data."""
    await _require_admin(session, admin)
    if kind not in DSR_KINDS:
        raise AppError(422, "Unknown request kind", "Use export or erase.")
    subject = await _subject(session, subject_id)
    received = received_at or datetime.now(UTC)
    req = DataSubjectRequest(
        subject_id=subject.id, kind=kind, status="open", received_at=received,
        due_at=received + timedelta(days=DSR_RESPONSE_DAYS), opened_by=f"user:{admin.id}",
    )
    session.add(req)
    await session.flush()
    await audit.record(session, f"user:{admin.id}", "dsr.request_opened", f"user:{subject.id}", {
        "request_id": str(req.id), "kind": kind})
    await session.commit()
    return _request_view(req)


async def _complete_open_requests(session: AsyncSession, subject_id: uuid.UUID, kind: str) -> int:
    rows = (await session.scalars(select(DataSubjectRequest).where(
        DataSubjectRequest.subject_id == subject_id, DataSubjectRequest.kind == kind,
        DataSubjectRequest.status == "open"))).all()
    now = datetime.now(UTC)
    for row in rows:
        row.status, row.completed_at = "completed", now
    return len(rows)


async def list_requests_page(
    session: AsyncSession, *, admin: User, status: str | None = None, overdue_only: bool = False,
    limit: int | None = None, cursor: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Keyset-paginated request ledger, newest first. Admin check runs before the page (cursors are not authz)."""
    await _require_admin(session, admin)
    size = clamp_limit(limit)
    stmt = select(DataSubjectRequest)
    if status:
        stmt = stmt.where(DataSubjectRequest.status == status)
    if overdue_only:
        stmt = stmt.where(DataSubjectRequest.status == "open", DataSubjectRequest.due_at < datetime.now(UTC))
    if cursor:
        ts, last_id = decode_cursor(cursor)
        stmt = stmt.where(tuple_(DataSubjectRequest.created_at, DataSubjectRequest.id) < tuple_(ts, last_id))
    stmt = stmt.order_by(DataSubjectRequest.created_at.desc(), DataSubjectRequest.id.desc()).limit(size + 1)
    rows = list((await session.scalars(stmt)).all())
    page, nxt = make_page(rows, size, lambda r: (r.created_at, r.id))
    now = datetime.now(UTC)
    return [_request_view(r, now) for r in page], nxt


async def export_subject_data(session: AsyncSession, *, admin: User, subject_id: uuid.UUID) -> dict[str, Any]:
    await _require_admin(session, admin)
    subject = await _subject(session, subject_id)

    convos = (await session.execute(
        select(Conversation).where(Conversation.user_id == subject.id).order_by(Conversation.created_at, Conversation.id)
    )).scalars().all()
    conversations = []
    for conv in convos:
        messages = (await session.execute(
            select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at, Message.id)
        )).scalars().all()
        conversations.append({
            "id": str(conv.id), "title": conv.title, "created_at": _iso(conv.created_at),
            "messages": [{"role": m.role, "content": m.content, "created_at": _iso(m.created_at)} for m in messages],
        })
    memories = (await session.execute(
        select(UserMemory).where(UserMemory.user_id == subject.id).order_by(UserMemory.created_at)
    )).scalars().all()
    notifications = (await session.execute(
        select(Notification).where(Notification.user_id == subject.id).order_by(Notification.created_at)
    )).scalars().all()
    owned = (await session.execute(
        select(Document.id, Document.title).where(Document.owner_id == subject.id)
    )).all()

    data = {
        "profile": {
            "id": str(subject.id), "email": subject.email, "display_name": subject.display_name,
            "status": subject.status, "locale": subject.locale, "time_zone": subject.time_zone,
            "created_at": _iso(subject.created_at),
        },
        "conversations": conversations,
        "memories": [{"text": m.text, "created_at": _iso(m.created_at)} for m in memories],
        "notifications": [{"kind": n.kind, "created_at": _iso(n.created_at)} for n in notifications],
        "owned_documents": [{"id": str(i), "title": t} for i, t in owned],
    }
    await audit.record(session, f"user:{admin.id}", "dsr.export", f"user:{subject.id}", {
        "conversations": len(conversations),
        "messages": sum(len(c["messages"]) for c in conversations),
        "memories": len(memories), "notifications": len(notifications), "owned_documents": len(owned),
    })
    await _complete_open_requests(session, subject.id, "export")
    await session.commit()
    return data


async def erase_subject_data(session: AsyncSession, *, admin: User, subject_id: uuid.UUID) -> dict[str, Any]:
    await _require_admin(session, admin)
    subject = await _subject(session, subject_id)
    if subject.status != "disabled":
        raise AppError(409, "User must be offboarded first",
                       "Deactivate the user (offboarding) before erasing their data.")

    held_chats = await session.scalar(select(func.count()).select_from(Conversation).where(
        Conversation.user_id == subject.id, Conversation.legal_hold.is_(True)))
    held_docs = await session.scalar(select(func.count()).select_from(Document).where(
        Document.owner_id == subject.id, Document.legal_hold.is_(True)))
    if held_chats or held_docs:
        raise AppError(409, "Legal hold",
                       "Erasure is blocked by a legal hold on this person's chats or documents.", "legal-hold")

    conv_ids = list((await session.execute(
        select(Conversation.id).where(Conversation.user_id == subject.id))).scalars().all())
    messages = 0
    if conv_ids:
        messages = await session.scalar(select(func.count()).select_from(Message).where(
            Message.conversation_id.in_(conv_ids))) or 0

    async def _delete(model, *conds) -> int:
        return (await session.execute(delete(model).where(*conds))).rowcount or 0

    # Messages, citations and feedback go with the conversation (ON DELETE CASCADE).
    conversations = await _delete(Conversation, Conversation.user_id == subject.id)
    memories = await _delete(UserMemory, UserMemory.user_id == subject.id)
    await _delete(UserMemorySetting, UserMemorySetting.user_id == subject.id)
    notifications = await _delete(Notification, Notification.user_id == subject.id)
    await _delete(AccessRequest, AccessRequest.requester_id == subject.id)
    api_keys = await _delete(ApiKey, ApiKey.user_id == subject.id)
    await _delete(LocalCredential, LocalCredential.user_id == subject.id)

    subject.email = f"erased-{subject.id}@erased.invalid"
    subject.display_name = "Erased user"
    subject.status = "disabled"

    result = {
        "conversations_deleted": conversations, "messages_deleted": messages,
        "memories_deleted": memories, "notifications_deleted": notifications, "api_keys_deleted": api_keys,
        "profile": "pseudonymised", "audit_log": "retained",
    }
    await audit.record(session, f"user:{admin.id}", "dsr.erase", f"user:{subject.id}", {
        k: v for k, v in result.items() if isinstance(v, int)})
    await _complete_open_requests(session, subject.id, "erase")
    await session.commit()
    return result


router = APIRouter(prefix="/api/v1/privacy", tags=["privacy"])


async def _admin_user(db: AsyncSession, sess: dict) -> User:
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None or user.status != "active":
        raise AppError(401, "Not authenticated")
    return user


@router.get("/subjects/{user_id}/export")
async def export_api(user_id: uuid.UUID, sess: dict = Depends(current_session),
                     db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_scope(sess, "evals")
    return await export_subject_data(db, admin=await _admin_user(db, sess), subject_id=user_id)


@router.post("/subjects/{user_id}/erase")
async def erase_api(user_id: uuid.UUID, sess: dict = Depends(current_session),
                    db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_scope(sess, "evals")
    return await erase_subject_data(db, admin=await _admin_user(db, sess), subject_id=user_id)


class RequestIn(BaseModel):
    subject_id: uuid.UUID
    kind: str


@router.post("/requests")
async def open_request_api(body: RequestIn, sess: dict = Depends(current_session),
                           db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_scope(sess, "evals")
    return await open_request(db, admin=await _admin_user(db, sess), subject_id=body.subject_id, kind=body.kind)


@router.get("/requests")
async def list_requests_api(
    status: str | None = None, overdue: bool = False, limit: int | None = None, cursor: str | None = None,
    sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    require_scope(sess, "evals")
    items, nxt = await list_requests_page(
        db, admin=await _admin_user(db, sess), status=status, overdue_only=overdue, limit=limit, cursor=cursor)
    return {"items": items, "next_cursor": nxt}
