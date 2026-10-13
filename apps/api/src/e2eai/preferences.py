"""User display preferences: time zone (NFR-20). Owner-only; the audit entry carries the zone name only."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .auth import current_session, require_scope
from .core.errors import AppError
from .core.timezones import DEFAULT_TIME_ZONE, validate_time_zone
from .db import User, get_session


async def set_time_zone(session: AsyncSession, *, user: User, time_zone: str) -> str:
    zone = validate_time_zone(time_zone)
    user.time_zone = zone
    await audit.record(session, f"user:{user.id}", "user.preferences.time_zone", f"user:{user.id}", {"time_zone": zone})
    await session.commit()
    return zone


class TimeZoneIn(BaseModel):
    time_zone: str


router = APIRouter(prefix="/api/v1/me", tags=["preferences"])


async def _user(db: AsyncSession, sess: dict) -> User:
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None or user.status != "active":
        raise AppError(401, "Not authenticated")
    return user


@router.get("/preferences")
async def get_preferences(sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)) -> dict:
    require_scope(sess, "chat")
    user = await _user(db, sess)
    return {"time_zone": user.time_zone or DEFAULT_TIME_ZONE, "locale": user.locale}


@router.put("/preferences/time-zone")
async def put_time_zone(
    body: TimeZoneIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)
) -> dict:
    require_scope(sess, "chat")
    return {"time_zone": await set_time_zone(db, user=await _user(db, sess), time_zone=body.time_zone)}
