"""Document lifecycle: review owner, review date, expiry (FR-D8).

Expired documents are excluded from retrieval/search/visible chunks by a SQL predicate on
`documents.expires_at` (see retrieval.py / documents.py), so an expired document leaves no
existence hint. Review reports contain only safe metadata (id, title, dates) for the review
owner; audit events never store titles or content.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .auth import current_session, require_scope
from .core.errors import AppError
from .db import DocPrincipal, Document, User, get_session

MAX_REVIEW_DAYS = 3650


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


async def _load(session: AsyncSession, document_id: uuid.UUID) -> Document:
    doc = await session.get(Document, document_id)
    if doc is None or doc.status == "purged":
        raise AppError(404, "Document not found")
    return doc


async def _is_document_owner(session: AsyncSession, user: User, document_id: uuid.UUID) -> bool:
    row = await session.scalar(select(DocPrincipal).where(
        DocPrincipal.document_id == document_id,
        DocPrincipal.principal == f"user:{user.id}",
        DocPrincipal.level == "owner",
    ))
    return row is not None


async def set_document_lifecycle(
    session: AsyncSession,
    *,
    actor: User,
    document_id: uuid.UUID,
    review_owner_id: uuid.UUID | None = None,
    review_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> Document:
    """Set review owner / review date / expiry. Only the document owner may change them."""
    doc = await _load(session, document_id)
    if not await _is_document_owner(session, actor, document_id):
        raise AppError(403, "Not allowed")
    review_at, expires_at = _utc(review_at), _utc(expires_at)
    eff_review = review_at or _utc(doc.review_at)
    eff_expiry = expires_at or _utc(doc.expires_at)
    if eff_review and eff_expiry and eff_expiry < eff_review:
        raise AppError(400, "Expiry must not be before the review date")
    if review_owner_id is not None:
        if await session.get(User, review_owner_id) is None:
            raise AppError(400, "Review owner not found")
        doc.review_owner_id = review_owner_id
    if review_at is not None:
        doc.review_at = review_at
    if expires_at is not None:
        doc.expires_at = expires_at
    details: dict[str, Any] = {}
    if review_owner_id is not None:
        details["review_owner_id"] = str(review_owner_id)
    if review_at is not None:
        details["review_at"] = review_at.isoformat()
    if expires_at is not None:
        details["expires_at"] = expires_at.isoformat()
    await audit.record(session, f"user:{actor.id}", "document.lifecycle.set", f"document:{document_id}", details)
    await session.commit()
    return doc


async def mark_reviewed(
    session: AsyncSession,
    *,
    actor: User,
    document_id: uuid.UUID,
    next_review_in_days: int = 180,
) -> Document:
    """The review owner (or document owner) confirms the document is still valid."""
    if not 1 <= next_review_in_days <= MAX_REVIEW_DAYS:
        raise AppError(400, "next_review_in_days out of range")
    doc = await _load(session, document_id)
    if doc.review_owner_id != actor.id and not await _is_document_owner(session, actor, document_id):
        raise AppError(403, "Not allowed")
    doc.review_at = datetime.now(UTC) + timedelta(days=next_review_in_days)
    await audit.record(
        session, f"user:{actor.id}", "document.lifecycle.reviewed", f"document:{document_id}",
        {"next_review_in_days": next_review_in_days, "review_at": doc.review_at.isoformat()},
    )
    await session.commit()
    return doc


async def list_due_reviews(
    session: AsyncSession, *, review_owner_id: uuid.UUID, now: datetime | None = None
) -> list[dict[str, Any]]:
    """Documents past their review date for one review owner (metadata only, no content)."""
    current = now or datetime.now(UTC)
    rows = (await session.execute(
        select(Document).where(
            Document.review_owner_id == review_owner_id,
            Document.status == "active",
            Document.review_at.is_not(None),
            Document.review_at <= current,
        ).order_by(Document.review_at.asc())
    )).scalars().all()
    return [
        {
            "document_id": str(d.id),
            "title": d.title,
            "review_at": _utc(d.review_at).isoformat(),
            "overdue_days": (current - _utc(d.review_at)).days,
            "expires_at": _utc(d.expires_at).isoformat() if d.expires_at else None,
        }
        for d in rows
    ]


class LifecycleIn(BaseModel):
    review_owner_id: uuid.UUID | None = None
    review_at: datetime | None = None
    expires_at: datetime | None = None


class ReviewedIn(BaseModel):
    next_review_in_days: int = 180


router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


async def _user(db: AsyncSession, sess: dict) -> User:
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None or user.status != "active":
        raise AppError(401, "Not authenticated")
    return user


@router.get("/reviews/due")
async def due_reviews_api(
    sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """FR-D8: documents whose review is due for the calling user."""
    require_scope(sess, "documents")
    user = await _user(db, sess)
    return {"reviews": await list_due_reviews(db, review_owner_id=user.id)}


@router.put("/{document_id}/lifecycle")
async def set_lifecycle_api(
    document_id: uuid.UUID,
    body: LifecycleIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    require_scope(sess, "documents")
    user = await _user(db, sess)
    doc = await set_document_lifecycle(
        db, actor=user, document_id=document_id, review_owner_id=body.review_owner_id,
        review_at=body.review_at, expires_at=body.expires_at,
    )
    return {
        "status": "ok",
        "review_owner_id": str(doc.review_owner_id) if doc.review_owner_id else None,
        "review_at": doc.review_at.isoformat() if doc.review_at else None,
        "expires_at": doc.expires_at.isoformat() if doc.expires_at else None,
    }


@router.post("/{document_id}/lifecycle/reviewed")
async def mark_reviewed_api(
    document_id: uuid.UUID,
    body: ReviewedIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    require_scope(sess, "documents")
    user = await _user(db, sess)
    doc = await mark_reviewed(db, actor=user, document_id=document_id, next_review_in_days=body.next_review_in_days)
    return {"status": "ok", "review_at": doc.review_at.isoformat()}
