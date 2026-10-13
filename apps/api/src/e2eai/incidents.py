"""AI incident management (FR-O8).

Lifecycle: reported -> triaged -> fixing -> fixed -> released -> closed.
Anyone active can report; admins triage and move the incident along. Traces are linked by plain id
only (no prompt/answer content). Free text is redacted for credential markers. Closing needs the
post-incident record. Every step is audited with ids/labels only; reporting notifies active admins.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .auth import current_session, require_scope
from .core.errors import AppError
from .core.pagination import clamp_limit, decode_cursor, make_page
from .db import AIIncident, Role, User, UserRole, get_session
from .legal_hold import is_admin

SEVERITIES = ("sev1", "sev2", "sev3", "sev4")
FLOW = ("reported", "triaged", "fixing", "fixed", "released", "closed")
MAX_TRACES = 200
_TRACE_ID = re.compile(r"^[A-Za-z0-9._:\-]{1,80}$")
_SECRET = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|apikey|credential|bearer)\b\s*[=:]?\s*\S*|\bsk-[A-Za-z0-9_\-]+"
)


def redact(text: str | None, limit: int = 2000) -> str:
    return _SECRET.sub("[redacted]", (text or "").strip())[:limit]


def _clean_title(title: str) -> str:
    cleaned = redact(title, 200)
    if not cleaned:
        raise AppError(400, "Invalid title")
    return cleaned


def _clean_traces(trace_ids: list[str], existing: list[str] | None = None) -> list[str]:
    out = list(existing or [])
    for tid in trace_ids:
        if not isinstance(tid, str) or not _TRACE_ID.match(tid):
            raise AppError(400, "Invalid trace id")
        if tid not in out:
            out.append(tid)
    if len(out) > MAX_TRACES:
        raise AppError(400, "Too many linked traces")
    return out


def summarize(inc: AIIncident) -> dict[str, Any]:
    return {
        "id": str(inc.id), "title": inc.title, "description": inc.description, "severity": inc.severity,
        "status": inc.status, "bot_id": str(inc.bot_id) if inc.bot_id else None, "trace_ids": list(inc.trace_ids or []),
        "assignee_id": inc.assignee_id, "fix_notes": inc.fix_notes, "release_ref": inc.release_ref,
        "postmortem": inc.postmortem, "reported_by": inc.reported_by,
        "closed_at": inc.closed_at.isoformat() if inc.closed_at else None,
    }


async def _get(session: AsyncSession, incident_id: uuid.UUID) -> AIIncident:
    inc = await session.get(AIIncident, incident_id)
    if inc is None:
        raise AppError(404, "Incident not found")
    return inc


async def _require_admin(session: AsyncSession, actor: User) -> None:
    if actor.status != "active" or not await is_admin(session, actor):
        raise AppError(403, "Not allowed")


async def report_incident(
    session: AsyncSession,
    *,
    actor: User,
    title: str,
    severity: str,
    description: str = "",
    trace_ids: list[str] | None = None,
    bot_id: uuid.UUID | None = None,
) -> AIIncident:
    if severity not in SEVERITIES:
        raise AppError(400, "Severity must be one of sev1, sev2, sev3, sev4")
    inc = AIIncident(
        title=_clean_title(title), description=redact(description), severity=severity, status="reported",
        bot_id=bot_id, trace_ids=_clean_traces(trace_ids or []), reported_by=str(actor.id),
    )
    session.add(inc)
    await session.flush()
    await audit.record(
        session, f"user:{actor.id}", "incident.report", f"incident:{inc.id}",
        {"severity": severity, "trace_count": len(inc.trace_ids)},
    )
    await session.commit()
    await _notify_admins(session, actor=actor, inc=inc)
    return inc


async def _notify_admins(session: AsyncSession, *, actor: User, inc: AIIncident) -> None:
    from .notifications import notify_incident_raised

    admin_ids = (
        await session.scalars(
            select(UserRole.user_id).join(Role, Role.id == UserRole.role_id).where(Role.name == "admin").distinct()
        )
    ).all()
    await notify_incident_raised(
        session, actor=actor, recipients=list(admin_ids), incident_id=inc.id, severity=inc.severity,
        title=inc.title, source="incident_management",
    )


async def add_traces(session: AsyncSession, *, actor: User, incident_id: uuid.UUID, trace_ids: list[str]) -> AIIncident:
    inc = await _get(session, incident_id)
    if inc.reported_by != str(actor.id):
        await _require_admin(session, actor)
    inc.trace_ids = _clean_traces(trace_ids, list(inc.trace_ids or []))
    await audit.record(
        session, f"user:{actor.id}", "incident.traces", f"incident:{inc.id}", {"trace_count": len(inc.trace_ids)}
    )
    await session.commit()
    return inc


async def transition_incident(
    session: AsyncSession,
    *,
    actor: User,
    incident_id: uuid.UUID,
    to_status: str,
    assignee_id: str | None = None,
    fix_notes: str | None = None,
    release_ref: str | None = None,
) -> AIIncident:
    await _require_admin(session, actor)
    inc = await _get(session, incident_id)
    if to_status not in FLOW or FLOW.index(to_status) != FLOW.index(inc.status) + 1:
        raise AppError(409, f"Cannot move from {inc.status} to {to_status}")
    if to_status == "fixed":
        notes = redact(fix_notes or inc.fix_notes)
        if not notes:
            raise AppError(400, "Fix notes are required")
        inc.fix_notes = notes
    if to_status == "released":
        ref = redact(release_ref, 200)
        if not ref:
            raise AppError(400, "Release reference is required")
        inc.release_ref = ref
    if to_status == "closed":
        if not inc.postmortem:
            raise AppError(409, "A post-incident record is required before closing")
        inc.closed_at = datetime.now(UTC)
    if assignee_id:
        inc.assignee_id = assignee_id[:80]
    inc.status = to_status
    await audit.record(
        session, f"user:{actor.id}", "incident.transition", f"incident:{inc.id}", {"to_status": to_status}
    )
    await session.commit()
    return inc


async def record_postmortem(
    session: AsyncSession,
    *,
    actor: User,
    incident_id: uuid.UUID,
    summary: str,
    root_cause: str,
    lessons: list[str] | None = None,
    action_items: list[str] | None = None,
) -> AIIncident:
    await _require_admin(session, actor)
    inc = await _get(session, incident_id)
    if inc.status not in ("fixed", "released", "closed"):
        raise AppError(409, "Post-incident record needs a fixed incident")
    if not redact(summary) or not redact(root_cause):
        raise AppError(400, "Summary and root cause are required")
    inc.postmortem = {
        "summary": redact(summary), "root_cause": redact(root_cause),
        "lessons": [redact(x, 500) for x in (lessons or [])][:20],
        "action_items": [redact(x, 500) for x in (action_items or [])][:20],
        "recorded_by": str(actor.id),
    }
    await audit.record(session, f"user:{actor.id}", "incident.postmortem", f"incident:{inc.id}", {})
    await session.commit()
    return inc


async def list_incidents_page(
    session: AsyncSession, *, status: str | None = None, limit: int | None = None, cursor: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Keyset-paginated incident list (NFR-20): newest first, ties broken by id. Caller enforces admin access."""
    size = clamp_limit(limit)
    stmt = select(AIIncident)
    if status:
        stmt = stmt.where(AIIncident.status == status)
    if cursor:
        ts, last_id = decode_cursor(cursor)
        stmt = stmt.where(tuple_(AIIncident.created_at, AIIncident.id) < tuple_(ts, last_id))
    stmt = stmt.order_by(AIIncident.created_at.desc(), AIIncident.id.desc()).limit(size + 1)
    rows = list((await session.scalars(stmt)).all())
    page, nxt = make_page(rows, size, lambda i: (i.created_at, i.id))
    return [summarize(i) for i in page], nxt


async def list_incidents(session: AsyncSession, *, status: str | None = None) -> list[dict[str, Any]]:
    stmt = select(AIIncident).order_by(AIIncident.created_at.desc()).limit(500)
    if status:
        stmt = stmt.where(AIIncident.status == status)
    return [summarize(i) for i in (await session.scalars(stmt)).all()]


class ReportIn(BaseModel):
    title: str
    severity: str
    description: str = ""
    trace_ids: list[str] = []
    bot_id: uuid.UUID | None = None


class TransitionIn(BaseModel):
    to_status: str
    assignee_id: str | None = None
    fix_notes: str | None = None
    release_ref: str | None = None


class PostmortemIn(BaseModel):
    summary: str
    root_cause: str
    lessons: list[str] = []
    action_items: list[str] = []


class TracesIn(BaseModel):
    trace_ids: list[str]


router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])


async def _user(db: AsyncSession, sess: dict) -> User:
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None or user.status != "active":
        raise AppError(401, "Not authenticated")
    return user


@router.post("")
async def report_api(
    body: ReportIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    require_scope(sess, "bots")
    inc = await report_incident(
        db, actor=await _user(db, sess), title=body.title, severity=body.severity,
        description=body.description, trace_ids=body.trace_ids, bot_id=body.bot_id,
    )
    return summarize(inc)


@router.get("")
async def list_api(
    status: str | None = None, limit: int | None = None, cursor: str | None = None,
    sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    require_scope(sess, "bots")
    await _require_admin(db, await _user(db, sess))
    items, next_cursor = await list_incidents_page(db, status=status, limit=limit, cursor=cursor)
    return {"incidents": items, "next_cursor": next_cursor}


@router.post("/{incident_id}/transition")
async def transition_api(
    incident_id: uuid.UUID, body: TransitionIn,
    sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    require_scope(sess, "admin")
    inc = await transition_incident(
        db, actor=await _user(db, sess), incident_id=incident_id, to_status=body.to_status,
        assignee_id=body.assignee_id, fix_notes=body.fix_notes, release_ref=body.release_ref,
    )
    return summarize(inc)


@router.post("/{incident_id}/postmortem")
async def postmortem_api(
    incident_id: uuid.UUID, body: PostmortemIn,
    sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    require_scope(sess, "admin")
    inc = await record_postmortem(
        db, actor=await _user(db, sess), incident_id=incident_id, summary=body.summary,
        root_cause=body.root_cause, lessons=body.lessons, action_items=body.action_items,
    )
    return summarize(inc)


@router.post("/{incident_id}/traces")
async def traces_api(
    incident_id: uuid.UUID, body: TracesIn,
    sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    require_scope(sess, "bots")
    inc = await add_traces(db, actor=await _user(db, sess), incident_id=incident_id, trace_ids=body.trace_ids)
    return summarize(inc)
