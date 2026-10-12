"""Approval workflow for high-risk bots (FR-P4).

The workflow is deterministic/offline: it records request and decision metadata,
updates AI inventory approval status, and audits safe fields only. It does not
store raw prompts, traces, documents, user-data samples, tokens, or credentials.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .auth import current_session, require_scope
from .core.errors import AppError
from .db import AIInventoryEntry, Bot, BotApproval, BotRiskClassification, User, get_session

VALID_APPROVAL_TYPES = ("high_risk_release",)
VALID_DECISIONS = ("approved", "rejected")
_FORBIDDEN_VALUE_MARKERS = ("password", "secret", "token", "api_key", "apikey", "credential", "bearer")


def _safe_text(value: str | None) -> str:
    text = (value or "").strip()[:500]
    if any(marker in text.lower() for marker in _FORBIDDEN_VALUE_MARKERS):
        return "[redacted]"
    return text


async def _bot_risk_tier(session: AsyncSession, bot_id: uuid.UUID) -> str:
    bot = await session.get(Bot, bot_id)
    if bot is None:
        raise AppError(404, "Bot not found")
    classification = await session.get(BotRiskClassification, bot_id)
    return classification.eu_ai_act_tier if classification is not None else "minimal"


async def request_bot_approval(
    session: AsyncSession,
    *,
    actor: User,
    bot_id: uuid.UUID,
    approval_type: str = "high_risk_release",
    rationale: str | None = None,
) -> BotApproval:
    """Create a pending FR-P4 bot approval request."""
    if approval_type not in VALID_APPROVAL_TYPES:
        raise AppError(400, f"Unknown approval type: {approval_type}")
    risk_tier = await _bot_risk_tier(session, bot_id)
    row = BotApproval(
        bot_id=bot_id,
        approval_type=approval_type,
        risk_tier=risk_tier,
        status="pending",
        rationale=_safe_text(rationale),
        requested_by=str(actor.id),
    )
    session.add(row)
    await session.flush()
    await audit.record(
        session,
        f"user:{actor.id}",
        "governance.bot_approval.request",
        f"bot:{bot_id}",
        {
            "approval_id": str(row.id),
            "bot_id": str(bot_id),
            "risk_tier": risk_tier,
            "status": "pending",
        },
    )
    await session.commit()
    return row


async def decide_bot_approval(
    session: AsyncSession,
    *,
    actor: User,
    approval_id: uuid.UUID,
    decision: str,
    note: str | None = None,
) -> BotApproval:
    """Approve or reject a pending FR-P4 bot approval and sync inventory state."""
    normalized = decision.lower().strip()
    if normalized not in VALID_DECISIONS:
        raise AppError(400, f"Unknown approval decision: {decision}")
    row = await session.get(BotApproval, approval_id)
    if row is None:
        raise AppError(404, "Approval request not found")
    if row.status != "pending":
        raise AppError(409, "Approval request already decided")

    row.status = normalized
    row.decision_note = _safe_text(note)
    row.decided_by = str(actor.id)
    row.decided_at = datetime.now(UTC)

    inventory = await session.scalar(select(AIInventoryEntry).where(AIInventoryEntry.bot_id == row.bot_id))
    if inventory is not None:
        inventory.approval_status = normalized
        inventory.updated_by = f"user:{actor.id}"

    await audit.record(
        session,
        f"user:{actor.id}",
        "governance.bot_approval.decide",
        f"bot_approval:{approval_id}",
        {
            "approval_id": str(row.id),
            "bot_id": str(row.bot_id),
            "risk_tier": row.risk_tier,
            "status": row.status,
            "decision": normalized,
        },
    )
    await session.commit()
    return row


async def list_bot_approvals(session: AsyncSession, *, bot_id: uuid.UUID | None = None) -> list[BotApproval]:
    stmt = select(BotApproval).order_by(BotApproval.created_at.asc(), BotApproval.id.asc())
    if bot_id is not None:
        stmt = stmt.where(BotApproval.bot_id == bot_id)
    return list((await session.execute(stmt)).scalars().all())


def safe_approval_summary(approval: BotApproval) -> dict[str, Any]:
    created_at = approval.__dict__.get("created_at")
    decided_at = approval.__dict__.get("decided_at")
    return {
        "id": str(approval.id),
        "bot_id": str(approval.bot_id),
        "approval_type": approval.approval_type,
        "risk_tier": approval.risk_tier,
        "status": approval.status,
        "rationale": approval.rationale,
        "decision_note": approval.decision_note,
        "requested_by": approval.requested_by,
        "decided_by": approval.decided_by,
        "created_at": created_at.isoformat() if created_at else None,
        "decided_at": decided_at.isoformat() if decided_at else None,
    }


class ApprovalRequestIn(BaseModel):
    bot_id: uuid.UUID
    approval_type: str = "high_risk_release"
    rationale: str | None = None


class ApprovalDecisionIn(BaseModel):
    decision: str
    note: str | None = None


router = APIRouter(prefix="/api/v1/governance", tags=["governance"])


@router.post("/bot-approvals")
async def request_bot_approval_api(
    body: ApprovalRequestIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """FR-P4: Request compliance approval for a bot."""
    require_scope(sess, "bots")
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None:
        raise AppError(401, "Not authenticated")
    approval = await request_bot_approval(
        db,
        actor=user,
        bot_id=body.bot_id,
        approval_type=body.approval_type,
        rationale=body.rationale,
    )
    return safe_approval_summary(approval)


@router.post("/bot-approvals/{approval_id}/decisions")
async def decide_bot_approval_api(
    approval_id: uuid.UUID,
    body: ApprovalDecisionIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """FR-P4: Approve or reject a bot approval request."""
    require_scope(sess, "bots")
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None:
        raise AppError(401, "Not authenticated")
    approval = await decide_bot_approval(db, actor=user, approval_id=approval_id, decision=body.decision, note=body.note)
    return safe_approval_summary(approval)


@router.get("/bot-approvals")
async def list_bot_approvals_api(
    bot_id: uuid.UUID | None = None,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """FR-P4: List bot approval workflow records."""
    require_scope(sess, "bots")
    rows = await list_bot_approvals(db, bot_id=bot_id)
    return {"items": [safe_approval_summary(row) for row in rows]}
