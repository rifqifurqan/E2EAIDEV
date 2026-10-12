"""Use-case intake form for Plan/Govern stage (FR-P1).

This deterministic/offline slice captures planning metadata only: problem,
users, success metrics, data sources, and systems to integrate. It deliberately
stores and returns no credentials or raw integration secrets.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .auth import current_session, require_scope
from .core.errors import AppError
from .db import UseCaseIntake, User, get_session

REQUIRED_SUCCESS_METRICS = ("task_success", "deflection", "time_saved")
_FORBIDDEN_MARKERS = ("password", "secret", "token", "api_key", "apikey", "credential", "bearer")


def _has_secret_marker(value: str) -> bool:
    return any(marker in value.lower() for marker in _FORBIDDEN_MARKERS)


def _safe_string(value: Any) -> str:
    text = str(value).strip()
    if not text:
        return ""
    if _has_secret_marker(text):
        return "[redacted]"
    return text[:500]


def _safe_list(values: list[Any]) -> list[str]:
    safe: list[str] = []
    for value in values:
        text = _safe_string(value)
        if text:
            safe.append(text)
    return safe


def _validate_success_metrics(success_metrics: dict[str, Any]) -> dict[str, str]:
    normalized = {str(key): _safe_string(value) for key, value in success_metrics.items()}
    missing = [key for key in REQUIRED_SUCCESS_METRICS if not normalized.get(key)]
    if missing:
        raise AppError(400, f"Missing success metrics: {', '.join(missing)}")
    return {key: normalized[key] for key in REQUIRED_SUCCESS_METRICS}


async def create_use_case_intake(
    session: AsyncSession,
    *,
    actor: User,
    title: str,
    problem: str,
    users: list[Any],
    success_metrics: dict[str, Any],
    data_sources: list[Any],
    systems_to_integrate: list[Any],
) -> UseCaseIntake:
    """Persist a FR-P1 use-case intake and audit safe metadata only."""
    safe_title = _safe_string(title)
    safe_problem = _safe_string(problem)
    safe_users = _safe_list(users)
    safe_metrics = _validate_success_metrics(success_metrics)
    safe_sources = _safe_list(data_sources)
    safe_systems = _safe_list(systems_to_integrate)

    missing_fields = []
    if not safe_title:
        missing_fields.append("title")
    if not safe_problem:
        missing_fields.append("problem")
    if not safe_users:
        missing_fields.append("users")
    if missing_fields:
        raise AppError(400, f"Missing use-case fields: {', '.join(missing_fields)}")

    intake = UseCaseIntake(
        owner_id=actor.id,
        title=safe_title,
        problem=safe_problem,
        users=safe_users,
        success_metrics=safe_metrics,
        data_sources=safe_sources,
        systems_to_integrate=safe_systems,
        status="submitted",
        created_by=f"user:{actor.id}",
        updated_by=f"user:{actor.id}",
    )
    session.add(intake)
    await session.flush()
    await audit.record(
        session,
        f"user:{actor.id}",
        "plan.use_case_intake.create",
        f"use_case_intake:{intake.id}",
        {
            "metrics": sorted(safe_metrics),
            "user_count": len(safe_users),
            "data_source_count": len(safe_sources),
            "system_count": len(safe_systems),
        },
    )
    await session.commit()
    return intake


def safe_use_case_summary(intake: UseCaseIntake) -> dict[str, Any]:
    """Return a secret-safe summary for API/UI consumers."""
    return {
        "id": str(intake.id),
        "title": intake.title,
        "problem": intake.problem,
        "users": list(intake.users or []),
        "success_metrics": dict(intake.success_metrics or {}),
        "data_sources": list(intake.data_sources or []),
        "systems_to_integrate": list(intake.systems_to_integrate or []),
        "status": intake.status,
        "owner_id": str(intake.owner_id),
        "created_at": intake.created_at.isoformat() if intake.created_at else None,
    }


class UseCaseIntakeIn(BaseModel):
    title: str
    problem: str
    users: list[Any]
    success_metrics: dict[str, Any]
    data_sources: list[Any] = []
    systems_to_integrate: list[Any] = []


router = APIRouter(prefix="/api/v1/plan", tags=["plan"])


@router.post("/use-cases")
async def create_use_case_intake_api(
    body: UseCaseIntakeIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """FR-P1: Submit a use-case intake form."""
    require_scope(sess, "bots")
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None:
        raise AppError(401, "Not authenticated")
    intake = await create_use_case_intake(
        db,
        actor=user,
        title=body.title,
        problem=body.problem,
        users=body.users,
        success_metrics=body.success_metrics,
        data_sources=body.data_sources,
        systems_to_integrate=body.systems_to_integrate,
    )
    return safe_use_case_summary(intake)
