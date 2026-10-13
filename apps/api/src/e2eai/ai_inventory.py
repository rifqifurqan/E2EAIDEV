"""AI inventory with model cards and system cards (FR-P3).

This slice keeps governance inventory deterministic and secret-safe: it stores
card metadata, owner, risk tier, status, and approval state, but never raw
prompts, traces, document text, credentials, or user data samples.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .auth import current_session, require_scope
from .bot_risk import VALID_EU_AI_ACT_TIERS
from .core.errors import AppError
from .core.pagination import clamp_limit, decode_cursor, make_page
from .db import AIInventoryEntry, Bot, BotRiskClassification, User, get_session

VALID_INVENTORY_KINDS = ("bot", "model")
VALID_INVENTORY_STATUSES = ("draft", "active", "retired")
VALID_APPROVAL_STATUSES = ("not_required", "pending", "approved", "rejected")
_FORBIDDEN_KEY_MARKERS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "credential",
    "bearer",
    "system_prompt",
    "prompt",
    "trace",
    "document_text",
    "raw_text",
)
_FORBIDDEN_VALUE_MARKERS = ("password", "secret", "token", "api_key", "apikey", "credential", "bearer")


def _has_marker(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in markers)


def _safe_card(card: dict[str, Any] | None) -> dict[str, Any]:
    """Return allowlisted card metadata with unsafe keys removed and values redacted.

    Model and system cards are descriptive governance metadata. A key that looks
    like a prompt, trace, document body, or credential is dropped; scalar values
    that mention credential markers are redacted. Nested values are summarized to
    avoid accidentally persisting raw payloads.
    """
    safe: dict[str, Any] = {}
    for key, value in (card or {}).items():
        safe_key = str(key).strip()[:80]
        if not safe_key or _has_marker(safe_key, _FORBIDDEN_KEY_MARKERS):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe_value: Any = "" if value is None else str(value).strip()[:500]
            if _has_marker(safe_value, _FORBIDDEN_VALUE_MARKERS):
                safe_value = "[redacted]"
        else:
            safe_value = "[structured metadata redacted]"
        safe[safe_key] = safe_value
    return safe


def _approval_status_for(risk_tier: str, requested: str | None = None) -> str:
    if requested is not None:
        status = requested.lower().strip()
        if status not in VALID_APPROVAL_STATUSES:
            raise AppError(400, f"Unknown approval status: {requested}")
        return status
    return "pending" if risk_tier in {"high", "unacceptable"} else "not_required"


async def _derive_bot_metadata(session: AsyncSession, bot_id: uuid.UUID) -> tuple[Bot, str]:
    bot = await session.get(Bot, bot_id)
    if bot is None:
        raise AppError(404, "Bot not found")
    classification = await session.get(BotRiskClassification, bot_id)
    return bot, (classification.eu_ai_act_tier if classification is not None else "minimal")


async def upsert_inventory_entry(
    session: AsyncSession,
    *,
    actor: User,
    kind: str,
    name: str | None = None,
    bot_id: uuid.UUID | None = None,
    owner_id: uuid.UUID | None = None,
    risk_tier: str | None = None,
    status: str = "draft",
    approval_status: str | None = None,
    model_card: dict[str, Any] | None = None,
    system_card: dict[str, Any] | None = None,
) -> AIInventoryEntry:
    """Create/update a FR-P3 inventory entry and audit safe metadata only."""
    normalized_kind = kind.lower().strip()
    if normalized_kind not in VALID_INVENTORY_KINDS:
        raise AppError(400, f"Unknown inventory kind: {kind}")

    normalized_status = status.lower().strip()
    if normalized_status not in VALID_INVENTORY_STATUSES:
        raise AppError(400, f"Unknown inventory status: {status}")

    derived_name = (name or "").strip()
    derived_owner_id = owner_id or actor.id
    derived_risk_tier = (risk_tier or "minimal").lower().strip()
    row: AIInventoryEntry | None = None

    if normalized_kind == "bot":
        if bot_id is None:
            raise AppError(400, "bot_id is required for bot inventory entries")
        bot, bot_risk_tier = await _derive_bot_metadata(session, bot_id)
        derived_name = derived_name or bot.name
        derived_owner_id = bot.owner_id
        derived_risk_tier = (risk_tier or bot_risk_tier).lower().strip()
        row = await session.scalar(select(AIInventoryEntry).where(AIInventoryEntry.bot_id == bot_id))
    else:
        if bot_id is not None:
            raise AppError(400, "model inventory entries cannot reference a bot")
        if not derived_name:
            raise AppError(400, "name is required for model inventory entries")
        row = await session.scalar(
            select(AIInventoryEntry).where(AIInventoryEntry.kind == "model", AIInventoryEntry.name == derived_name)
        )

    if derived_risk_tier not in VALID_EU_AI_ACT_TIERS:
        raise AppError(400, f"Unknown risk tier: {derived_risk_tier}")

    if row is None:
        row = AIInventoryEntry(kind=normalized_kind, bot_id=bot_id)
        session.add(row)
    row.kind = normalized_kind
    row.bot_id = bot_id
    row.name = derived_name[:200]
    row.owner_id = derived_owner_id
    row.risk_tier = derived_risk_tier
    row.status = normalized_status
    row.approval_status = _approval_status_for(derived_risk_tier, approval_status)
    row.model_card = _safe_card(model_card)
    row.system_card = _safe_card(system_card)
    row.updated_by = f"user:{actor.id}"

    await session.flush()
    await audit.record(
        session,
        f"user:{actor.id}",
        "governance.ai_inventory.upsert",
        f"ai_inventory:{row.id}",
        {
            "kind": row.kind,
            "risk_tier": row.risk_tier,
            "status": row.status,
            "model_card_keys": sorted(row.model_card),
            "system_card_keys": sorted(row.system_card),
        },
    )
    await session.commit()
    return row


async def list_inventory(session: AsyncSession, *, kind: str | None = None) -> list[AIInventoryEntry]:
    stmt = select(AIInventoryEntry).order_by(AIInventoryEntry.created_at.asc(), AIInventoryEntry.id.asc())
    if kind is not None:
        normalized_kind = kind.lower().strip()
        if normalized_kind not in VALID_INVENTORY_KINDS:
            raise AppError(400, f"Unknown inventory kind: {kind}")
        stmt = stmt.where(AIInventoryEntry.kind == normalized_kind)
    return list((await session.execute(stmt)).scalars().all())


async def list_inventory_page(
    session: AsyncSession, *, kind: str | None = None, limit: int | None = None, cursor: str | None = None
) -> tuple[list[AIInventoryEntry], str | None]:
    """Keyset-paginated inventory (NFR-20): newest first, ties broken by id."""
    size = clamp_limit(limit)
    stmt = select(AIInventoryEntry)
    if kind is not None:
        normalized_kind = kind.lower().strip()
        if normalized_kind not in VALID_INVENTORY_KINDS:
            raise AppError(400, f"Unknown inventory kind: {kind}")
        stmt = stmt.where(AIInventoryEntry.kind == normalized_kind)
    if cursor:
        ts, last_id = decode_cursor(cursor)
        stmt = stmt.where(tuple_(AIInventoryEntry.created_at, AIInventoryEntry.id) < tuple_(ts, last_id))
    stmt = stmt.order_by(AIInventoryEntry.created_at.desc(), AIInventoryEntry.id.desc()).limit(size + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    return make_page(rows, size, lambda e: (e.created_at, e.id))


def safe_inventory_summary(entry: AIInventoryEntry) -> dict[str, Any]:
    updated_at = entry.__dict__.get("updated_at")
    return {
        "id": str(entry.id),
        "kind": entry.kind,
        "bot_id": str(entry.bot_id) if entry.bot_id else None,
        "name": entry.name,
        "owner_id": str(entry.owner_id),
        "risk_tier": entry.risk_tier,
        "status": entry.status,
        "approval_status": entry.approval_status,
        "model_card": dict(entry.model_card or {}),
        "system_card": dict(entry.system_card or {}),
        "updated_by": entry.updated_by,
        "updated_at": updated_at.isoformat() if updated_at else None,
    }


class InventoryEntryIn(BaseModel):
    kind: str
    name: str | None = None
    bot_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    risk_tier: str | None = None
    status: str = "draft"
    approval_status: str | None = None
    model_card: dict[str, Any] = {}
    system_card: dict[str, Any] = {}


router = APIRouter(prefix="/api/v1/governance", tags=["governance"])


@router.put("/ai-inventory")
async def upsert_inventory_entry_api(
    body: InventoryEntryIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """FR-P3: Create or update an AI inventory entry."""
    require_scope(sess, "bots")
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None:
        raise AppError(401, "Not authenticated")
    entry = await upsert_inventory_entry(
        db,
        actor=user,
        kind=body.kind,
        name=body.name,
        bot_id=body.bot_id,
        owner_id=body.owner_id,
        risk_tier=body.risk_tier,
        status=body.status,
        approval_status=body.approval_status,
        model_card=body.model_card,
        system_card=body.system_card,
    )
    return safe_inventory_summary(entry)


@router.get("/ai-inventory")
async def list_inventory_api(
    kind: str | None = Query(default=None),
    limit: int | None = Query(default=None),
    cursor: str | None = Query(default=None),
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """FR-P3: List AI inventory entries."""
    require_scope(sess, "bots")
    rows, next_cursor = await list_inventory_page(db, kind=kind, limit=limit, cursor=cursor)
    return {"items": [safe_inventory_summary(row) for row in rows], "next_cursor": next_cursor}
