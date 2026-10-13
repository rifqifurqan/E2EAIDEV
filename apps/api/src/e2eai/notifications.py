"""In-app notification helpers and API boundary (FR-F11/FR-C10).

Notification details intentionally contain safe metadata only: IDs, titles/names,
status/severity labels, versions, and actor IDs. Raw prompts, traces, answers,
document contents, tokens, credentials, and descriptions stay out of notifications.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .auth import current_session, require_scope
from .core.errors import AppError
from .core.pagination import clamp_limit, decode_cursor, make_page
from .db import Notification, User, get_session

SAFE_NOTIFICATION_KINDS: tuple[str, ...] = (
    "document.shared",
    "access_request.approved",
    "review.assigned",
    "release.approved",
    "incident.raised",
    "slo.alert.fired",
    "finops.budget.alert.fired",
    "dsr.deadline",
)


def _str_id(value: uuid.UUID | str) -> str:
    return str(value)


async def _active_recipient(session: AsyncSession, user: User | uuid.UUID) -> User | None:
    recipient = await session.get(User, user) if isinstance(user, uuid.UUID) else user
    if recipient is None or recipient.status != "active":
        return None
    return recipient


async def _create_notification(
    session: AsyncSession,
    *,
    actor: User,
    recipient: User | uuid.UUID,
    kind: str,
    details: dict[str, Any],
    audit_action: str,
    audit_target: str,
) -> Notification | None:
    """Create one safe notification, skipping actor self-notifications and inactive users."""
    if kind not in SAFE_NOTIFICATION_KINDS:
        raise AppError(400, "Unsupported notification kind")
    user = await _active_recipient(session, recipient)
    if user is None or user.id == actor.id:
        return None
    notification = Notification(user_id=user.id, kind=kind, details=details)
    session.add(notification)
    await audit.record(
        session,
        f"user:{actor.id}",
        audit_action,
        audit_target,
        {"recipient_id": str(user.id), "kind": kind},
    )
    await session.commit()
    return notification


async def notify_review_assigned(
    session: AsyncSession,
    *,
    actor: User,
    reviewer: User | uuid.UUID,
    review_type: str,
    target_id: uuid.UUID | str,
    title: str,
    priority: str | None = None,
    **_: Any,
) -> Notification | None:
    """Notify a reviewer that a safe review task was assigned (FR-F11).

    Extra keyword arguments are accepted but ignored so callers cannot accidentally
    smuggle raw prompts, answers, traces, tokens, or document contents into the
    notification payload.
    """
    details: dict[str, Any] = {
        "review_type": review_type,
        "target_id": _str_id(target_id),
        "title": title,
        "assigned_by": str(actor.id),
    }
    if priority:
        details["priority"] = priority
    return await _create_notification(
        session,
        actor=actor,
        recipient=reviewer,
        kind="review.assigned",
        details=details,
        audit_action="notification.review.assigned",
        audit_target=f"review:{_str_id(target_id)}",
    )


async def notify_release_approved(
    session: AsyncSession,
    *,
    actor: User,
    recipient: User | uuid.UUID,
    bot_id: uuid.UUID | str,
    bot_name: str,
    version: int,
    environment: str = "prod",
    approval_id: uuid.UUID | str | None = None,
    **_: Any,
) -> Notification | None:
    """Notify a user that a bot release was approved (FR-F11)."""
    details: dict[str, Any] = {
        "bot_id": _str_id(bot_id),
        "bot_name": bot_name,
        "version": int(version),
        "environment": environment,
        "approved_by": str(actor.id),
    }
    if approval_id is not None:
        details["approval_id"] = _str_id(approval_id)
    return await _create_notification(
        session,
        actor=actor,
        recipient=recipient,
        kind="release.approved",
        details=details,
        audit_action="notification.release.approved",
        audit_target=f"bot:{_str_id(bot_id)}",
    )


async def notify_incident_raised(
    session: AsyncSession,
    *,
    actor: User,
    recipients: Iterable[User | uuid.UUID],
    incident_id: uuid.UUID | str,
    severity: str,
    title: str,
    source: str = "manual",
    **_: Any,
) -> list[Notification]:
    """Notify active recipients that an incident was raised (FR-F11).

    The incident payload is limited to routing metadata. Full descriptions,
    traces, prompts, answers, and tool payloads belong in the incident record,
    not in the in-app notification details.
    """
    notifications: list[Notification] = []
    details = {
        "incident_id": _str_id(incident_id),
        "severity": severity,
        "title": title,
        "source": source,
        "raised_by": str(actor.id),
    }
    seen: set[uuid.UUID] = set()
    for recipient in recipients:
        user = await _active_recipient(session, recipient)
        if user is None or user.id in seen:
            continue
        seen.add(user.id)
        created = await _create_notification(
            session,
            actor=actor,
            recipient=user,
            kind="incident.raised",
            details=details,
            audit_action="notification.incident.raised",
            audit_target=f"incident:{_str_id(incident_id)}",
        )
        if created is not None:
            notifications.append(created)
    return notifications


class ReviewAssignedIn(BaseModel):
    reviewer_id: uuid.UUID
    review_type: str
    target_id: uuid.UUID
    title: str
    priority: str | None = None


class ReleaseApprovedIn(BaseModel):
    recipient_id: uuid.UUID
    bot_id: uuid.UUID
    bot_name: str
    version: int = Field(ge=1)
    environment: str = "prod"
    approval_id: uuid.UUID | None = None


class IncidentRaisedIn(BaseModel):
    recipient_ids: list[uuid.UUID]
    incident_id: uuid.UUID
    severity: str
    title: str
    source: str = "manual"


router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


async def _current_user(db: AsyncSession, sess: dict) -> User:
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None or user.status != "active":
        raise AppError(401, "User not found")
    return user


async def list_notifications_page(
    session: AsyncSession, *, user: User, unread_only: bool = False,
    limit: int | None = None, cursor: str | None = None,
) -> tuple[list[Notification], str | None]:
    """Keyset-paginated, owner-scoped notification list (NFR-20): newest first, ties broken by id."""
    size = clamp_limit(limit)
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    if cursor:
        ts, last_id = decode_cursor(cursor)
        stmt = stmt.where(tuple_(Notification.created_at, Notification.id) < tuple_(ts, last_id))
    stmt = stmt.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(size + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    return make_page(rows, size, lambda n: (n.created_at, n.id))


@router.get("")
async def list_my_notifications(
    unread_only: bool = False,
    limit: int | None = None,
    cursor: str | None = None,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    require_scope(sess, "notifications")
    user = await _current_user(db, sess)
    rows, next_cursor = await list_notifications_page(db, user=user, unread_only=unread_only, limit=limit, cursor=cursor)
    return {
        "next_cursor": next_cursor,
        "notifications": [
            {
                "id": str(n.id),
                "kind": n.kind,
                "details": n.details,
                "read_at": n.read_at.isoformat() if n.read_at else None,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in rows
        ]
    }


@router.post("/review-assigned")
async def review_assigned_api(
    body: ReviewAssignedIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    require_scope(sess, "notifications")
    actor = await _current_user(db, sess)
    notification = await notify_review_assigned(
        db,
        actor=actor,
        reviewer=body.reviewer_id,
        review_type=body.review_type,
        target_id=body.target_id,
        title=body.title,
        priority=body.priority,
    )
    return {"status": "created" if notification else "skipped"}


@router.post("/release-approved")
async def release_approved_api(
    body: ReleaseApprovedIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    require_scope(sess, "notifications")
    actor = await _current_user(db, sess)
    notification = await notify_release_approved(
        db,
        actor=actor,
        recipient=body.recipient_id,
        bot_id=body.bot_id,
        bot_name=body.bot_name,
        version=body.version,
        environment=body.environment,
        approval_id=body.approval_id,
    )
    return {"status": "created" if notification else "skipped"}


@router.post("/incident-raised")
async def incident_raised_api(
    body: IncidentRaisedIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    require_scope(sess, "notifications")
    actor = await _current_user(db, sess)
    created = await notify_incident_raised(
        db,
        actor=actor,
        recipients=body.recipient_ids,
        incident_id=body.incident_id,
        severity=body.severity,
        title=body.title,
        source=body.source,
    )
    return {"status": "created", "count": len(created)}
