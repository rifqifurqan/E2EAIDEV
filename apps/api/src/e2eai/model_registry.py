"""Model registry with lineage, eval scores, and approval status (FR-M7).

Versioned entries (name + version) carry sanitized lineage (base model, source, dataset reference,
parent version), eval scores snapshotted from existing EvalRun metrics (numeric only), and an
admin-controlled approval status. Approval needs at least one eval score. Audit events store only
ids/names/versions/decisions, never lineage values or scores.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .ai_inventory import _safe_card
from .auth import current_session, require_scope
from .core.errors import AppError
from .db import EvalRun, ModelRegistryEntry, User, get_session
from .legal_hold import is_admin

VALID_DECISIONS = ("approved", "rejected")
MAX_CHAIN = 50


def _numeric_metrics(metrics: dict[str, Any] | None) -> dict[str, float]:
    return {
        str(k)[:80]: float(v)
        for k, v in (metrics or {}).items()
        if isinstance(v, (int, float)) and not isinstance(v, bool)
    }


def _clean(value: str, field: str, limit: int) -> str:
    cleaned = (value or "").strip()
    if not cleaned or len(cleaned) > limit:
        raise AppError(400, f"Invalid {field}")
    return cleaned


def summarize(entry: ModelRegistryEntry) -> dict[str, Any]:
    return {
        "name": entry.name,
        "version": entry.version,
        "parent_version": entry.parent_version,
        "lineage": entry.lineage or {},
        "eval_scores": entry.eval_scores or {},
        "approval_status": entry.approval_status,
        "approved_by": entry.approved_by,
    }


async def _get(session: AsyncSession, name: str, version: str) -> ModelRegistryEntry:
    entry = await session.scalar(
        select(ModelRegistryEntry).where(ModelRegistryEntry.name == name, ModelRegistryEntry.version == version)
    )
    if entry is None:
        raise AppError(404, "Model version not found")
    return entry


async def register_model_version(
    session: AsyncSession,
    *,
    actor: User,
    name: str,
    version: str,
    parent_version: str | None = None,
    lineage: dict[str, Any] | None = None,
) -> ModelRegistryEntry:
    name, version = _clean(name, "name", 200), _clean(version, "version", 64)
    existing = await session.scalar(
        select(ModelRegistryEntry).where(ModelRegistryEntry.name == name, ModelRegistryEntry.version == version)
    )
    if existing is not None:
        raise AppError(409, "Model version already registered")
    if parent_version is not None:
        parent = await session.scalar(
            select(ModelRegistryEntry).where(ModelRegistryEntry.name == name, ModelRegistryEntry.version == parent_version)
        )
        if parent is None:
            raise AppError(400, "Parent version not found")
    entry = ModelRegistryEntry(
        name=name, version=version, parent_version=parent_version,
        lineage=_safe_card(lineage), eval_scores={}, approval_status="pending",
        registered_by=str(actor.id),
    )
    session.add(entry)
    await audit.record(
        session, f"user:{actor.id}", "model_registry.register", f"model:{name}@{version}",
        {"name": name, "version": version, "parent_version": parent_version},
    )
    await session.commit()
    return entry


async def attach_eval_run(
    session: AsyncSession, *, actor: User, name: str, version: str, run_id: uuid.UUID
) -> ModelRegistryEntry:
    entry = await _get(session, name, version)
    run = await session.get(EvalRun, run_id)
    if run is None:
        raise AppError(404, "Eval run not found")
    scores = dict(entry.eval_scores or {})
    scores[str(run.id)] = {"adapter": run.adapter, "metrics": _numeric_metrics(run.metrics)}
    entry.eval_scores = scores  # reassign so JSONB change is detected
    await audit.record(
        session, f"user:{actor.id}", "model_registry.eval_attached", f"model:{name}@{version}",
        {"name": name, "version": version, "run_id": str(run.id)},
    )
    await session.commit()
    return entry


async def decide_approval(
    session: AsyncSession, *, actor: User, name: str, version: str, decision: str
) -> ModelRegistryEntry:
    if decision not in VALID_DECISIONS:
        raise AppError(400, "Decision must be approved or rejected")
    if actor.status != "active" or not await is_admin(session, actor):
        raise AppError(403, "Not allowed")
    entry = await _get(session, name, version)
    if decision == "approved" and not entry.eval_scores:
        raise AppError(409, "Approval requires at least one eval score")
    entry.approval_status = decision
    entry.approved_by = str(actor.id)
    await audit.record(
        session, f"user:{actor.id}", "model_registry.decide", f"model:{name}@{version}",
        {"name": name, "version": version, "decision": decision},
    )
    await session.commit()
    return entry


async def get_lineage_chain(session: AsyncSession, *, name: str, version: str) -> list[dict[str, Any]]:
    """Walk parent_version links from the given version back to the root (newest first)."""
    chain: list[dict[str, Any]] = []
    seen: set[str] = set()
    current: str | None = version
    while current is not None and current not in seen and len(chain) < MAX_CHAIN:
        entry = await _get(session, name, current)
        chain.append(summarize(entry))
        seen.add(current)
        current = entry.parent_version
    return chain


async def list_models(session: AsyncSession, *, name: str | None = None) -> list[dict[str, Any]]:
    stmt = select(ModelRegistryEntry).order_by(ModelRegistryEntry.name, ModelRegistryEntry.version)
    if name:
        stmt = stmt.where(ModelRegistryEntry.name == name)
    return [summarize(e) for e in (await session.scalars(stmt)).all()]


class RegisterIn(BaseModel):
    name: str
    version: str
    parent_version: str | None = None
    lineage: dict[str, Any] = {}


class AttachRunIn(BaseModel):
    run_id: uuid.UUID


class DecisionIn(BaseModel):
    decision: str


router = APIRouter(prefix="/api/v1/model-registry", tags=["model-registry"])


async def _user(db: AsyncSession, sess: dict) -> User:
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None or user.status != "active":
        raise AppError(401, "Not authenticated")
    return user


@router.get("")
async def list_models_api(
    name: str | None = None, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    require_scope(sess, "evals")
    await _user(db, sess)
    return {"models": await list_models(db, name=name)}


@router.post("")
async def register_model_api(
    body: RegisterIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    require_scope(sess, "evals")
    entry = await register_model_version(
        db, actor=await _user(db, sess), name=body.name, version=body.version,
        parent_version=body.parent_version, lineage=body.lineage,
    )
    return summarize(entry)


@router.post("/{name}/{version}/eval-runs")
async def attach_eval_run_api(
    name: str, version: str, body: AttachRunIn,
    sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    require_scope(sess, "evals")
    entry = await attach_eval_run(db, actor=await _user(db, sess), name=name, version=version, run_id=body.run_id)
    return summarize(entry)


@router.post("/{name}/{version}/decision")
async def decide_api(
    name: str, version: str, body: DecisionIn,
    sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    require_scope(sess, "admin")
    entry = await decide_approval(db, actor=await _user(db, sess), name=name, version=version, decision=body.decision)
    return summarize(entry)


@router.get("/{name}/{version}/lineage")
async def lineage_api(
    name: str, version: str, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    require_scope(sess, "evals")
    await _user(db, sess)
    return {"chain": await get_lineage_chain(db, name=name, version=version)}
