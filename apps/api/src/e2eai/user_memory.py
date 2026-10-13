"""Long-term user memory (FR-B2).

Opt-in per user (off by default). Items are PII-masked and secret-redacted before storage. Only the
owning user can list or delete their memory; a foreign id returns the same 404 as a missing one.
Audit events carry ids/counts only, never the memory text. Deterministic/offline: no model calls.
`recall_context` returns plain strings that the chat pipeline may prepend as untrusted context.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import delete, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .auth import current_session, require_scope
from .core.errors import AppError
from .core.pagination import clamp_limit, decode_cursor, make_page
from .db import User, UserMemory, UserMemorySetting, get_session
from .incidents import redact
from .pii import mask_text

MAX_MEMORY_CHARS = 500
MAX_ITEMS_PER_USER = 200


def _actor(user: User) -> str:
    return f"user:{user.id}"


def _clean(text: str) -> str:
    cleaned = redact(mask_text((text or "").strip()), MAX_MEMORY_CHARS)
    if not cleaned.strip():
        raise AppError(400, "Memory text is empty")
    return cleaned


def _view(item: UserMemory) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "text": item.text,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


async def is_enabled(session: AsyncSession, user: User) -> bool:
    setting = await session.get(UserMemorySetting, user.id)
    return bool(setting and setting.enabled)


async def set_enabled(session: AsyncSession, *, user: User, enabled: bool) -> dict[str, bool]:
    setting = await session.get(UserMemorySetting, user.id)
    if setting is None:
        session.add(UserMemorySetting(user_id=user.id, enabled=enabled))
    else:
        setting.enabled = enabled
    await audit.record(session, _actor(user), "memory.enable" if enabled else "memory.disable", f"user:{user.id}", {})
    await session.commit()
    return {"enabled": enabled}


async def remember(session: AsyncSession, *, user: User, text: str) -> dict[str, Any]:
    if user.status != "active":
        raise AppError(401, "Not authenticated")
    if not await is_enabled(session, user):
        raise AppError(409, "Long-term memory is turned off")
    cleaned = _clean(text)
    count = await session.scalar(select(func.count()).select_from(UserMemory).where(UserMemory.user_id == user.id))
    if (count or 0) >= MAX_ITEMS_PER_USER:
        raise AppError(409, "Memory limit reached")
    item = UserMemory(user_id=user.id, text=cleaned)
    session.add(item)
    await session.flush()
    await audit.record(session, _actor(user), "memory.add", f"memory:{item.id}", {"chars": len(cleaned)})
    await session.commit()
    return _view(item)


async def list_memories(session: AsyncSession, *, user: User) -> list[dict[str, Any]]:
    rows = await session.scalars(
        select(UserMemory)
        .where(UserMemory.user_id == user.id)
        .order_by(UserMemory.created_at.desc(), UserMemory.id.desc())
    )
    return [_view(r) for r in rows.all()]


async def list_memories_page(
    session: AsyncSession, *, user: User, limit: int | None = None, cursor: str | None = None
) -> tuple[list[dict[str, Any]], str | None]:
    """Keyset-paginated, owner-scoped memory list (NFR-20): newest first, ties broken by id."""
    size = clamp_limit(limit)
    stmt = select(UserMemory).where(UserMemory.user_id == user.id)
    if cursor:
        ts, last_id = decode_cursor(cursor)
        stmt = stmt.where(tuple_(UserMemory.created_at, UserMemory.id) < tuple_(ts, last_id))
    stmt = stmt.order_by(UserMemory.created_at.desc(), UserMemory.id.desc()).limit(size + 1)
    rows = list((await session.scalars(stmt)).all())
    page, nxt = make_page(rows, size, lambda m: (m.created_at, m.id))
    return [_view(r) for r in page], nxt


async def delete_memory(session: AsyncSession, *, user: User, memory_id: str | uuid.UUID) -> None:
    try:
        mid = memory_id if isinstance(memory_id, uuid.UUID) else uuid.UUID(str(memory_id))
    except ValueError:
        raise AppError(404, "Memory not found") from None
    item = await session.get(UserMemory, mid)
    if item is None or item.user_id != user.id:
        raise AppError(404, "Memory not found")
    await session.delete(item)
    await audit.record(session, _actor(user), "memory.delete", f"memory:{mid}", {})
    await session.commit()


async def clear_memories(session: AsyncSession, *, user: User) -> int:
    result = await session.execute(delete(UserMemory).where(UserMemory.user_id == user.id))
    removed = int(result.rowcount or 0)
    await audit.record(session, _actor(user), "memory.clear", f"user:{user.id}", {"removed": removed})
    await session.commit()
    return removed


async def recall_context(session: AsyncSession, *, user: User, limit: int = 5) -> list[str]:
    """Newest-first memory strings for prompt context; empty unless the user opted in."""
    if user.status != "active" or not await is_enabled(session, user):
        return []
    rows = await session.scalars(
        select(UserMemory.text)
        .where(UserMemory.user_id == user.id)
        .order_by(UserMemory.created_at.desc(), UserMemory.id.desc())
        .limit(max(0, min(limit, 20)))
    )
    return list(rows.all())


class MemoryIn(BaseModel):
    text: str


class SettingsIn(BaseModel):
    enabled: bool


router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


async def _user(db: AsyncSession, sess: dict) -> User:
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None or user.status != "active":
        raise AppError(401, "Not authenticated")
    return user


@router.get("")
async def list_api(
    limit: int | None = Query(default=None),
    cursor: str | None = Query(default=None),
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    require_scope(sess, "chat")
    user = await _user(db, sess)
    items, next_cursor = await list_memories_page(db, user=user, limit=limit, cursor=cursor)
    return {"enabled": await is_enabled(db, user), "items": items, "next_cursor": next_cursor}


@router.post("")
async def add_api(
    body: MemoryIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    require_scope(sess, "chat")
    return await remember(db, user=await _user(db, sess), text=body.text)


@router.delete("")
async def clear_api(sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)) -> dict[str, int]:
    require_scope(sess, "chat")
    return {"removed": await clear_memories(db, user=await _user(db, sess))}


@router.put("/settings")
async def settings_api(
    body: SettingsIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)
) -> dict[str, bool]:
    require_scope(sess, "chat")
    return await set_enabled(db, user=await _user(db, sess), enabled=body.enabled)


@router.delete("/{memory_id}")
async def delete_api(
    memory_id: str, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)
) -> dict[str, str]:
    require_scope(sess, "chat")
    await delete_memory(db, user=await _user(db, sess), memory_id=memory_id)
    return {"status": "deleted"}
