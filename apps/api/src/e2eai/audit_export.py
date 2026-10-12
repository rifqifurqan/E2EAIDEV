"""Audit export to SIEM sinks (FR-F10).

Exports hash-chained audit events as secret-safe syslog lines, OpenTelemetry log
records, or webhook JSON payloads. The exporter includes detail keys but never
exports raw detail values that may contain credentials or sensitive payloads.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import current_session, require_scope
from .core.errors import AppError
from .db import AuditEntry, get_session

VALID_SINKS = ("syslog", "otel", "webhook")


def _safe_keys(details: dict[str, Any]) -> list[str]:
    return sorted(str(key)[:80] for key in (details or {}))


def _public_keys(details: dict[str, Any]) -> list[str]:
    sensitive = ("password", "secret", "token", "api_key", "apikey", "credential", "bearer")
    return [key for key in _safe_keys(details) if not any(marker in key.lower() for marker in sensitive)]


def _syslog(entry: AuditEntry) -> str:
    return (
        f"{entry.at.isoformat()} e2eai audit "
        f"action={entry.action} actor={entry.actor} target={entry.target} "
        f"seq={entry.seq} hash={entry.hash} detail_keys={','.join(_public_keys(entry.details))}"
    )


def _otel(entry: AuditEntry) -> dict[str, Any]:
    return {
        "time_unix_nano": int(entry.at.timestamp() * 1_000_000_000),
        "severity_text": "INFO",
        "body": entry.action,
        "attributes": {
            "audit.seq": entry.seq,
            "audit.actor": entry.actor,
            "audit.action": entry.action,
            "audit.target": entry.target,
            "audit.hash": entry.hash,
            "audit.prev_hash": entry.prev_hash,
            "audit.detail_keys": _safe_keys(entry.details),
        },
    }


def _webhook(entry: AuditEntry) -> dict[str, Any]:
    return {
        "seq": entry.seq,
        "at": entry.at.isoformat(),
        "actor": entry.actor,
        "action": entry.action,
        "target": entry.target,
        "hash": entry.hash,
        "prev_hash": entry.prev_hash,
        "detail_keys": _safe_keys(entry.details),
    }


async def export_audit_events(
    session: AsyncSession,
    *,
    sink: str,
    after_seq: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    """Export a page of audit rows for a SIEM sink, cursoring by audit seq."""
    if sink not in VALID_SINKS:
        raise AppError(400, f"Unknown audit export sink: {sink}")
    safe_limit = max(1, min(int(limit), 1000))
    rows = list(
        (
            await session.execute(
                select(AuditEntry)
                .where(AuditEntry.seq > after_seq)
                .order_by(AuditEntry.seq.asc())
                .limit(safe_limit + 1)
            )
        ).scalars().all()
    )
    has_more = len(rows) > safe_limit
    rows = rows[:safe_limit]
    if sink == "syslog":
        events = [_syslog(row) for row in rows]
    elif sink == "otel":
        events = [_otel(row) for row in rows]
    else:
        events = [_webhook(row) for row in rows]
    cursor = rows[-1].seq if rows else after_seq
    return {"sink": sink, "cursor": cursor, "has_more": has_more, "events": events}


class AuditExportIn(BaseModel):
    sink: str
    after_seq: int = 0
    limit: int = 100


router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.post("/export")
async def export_audit_events_api(
    body: AuditExportIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """FR-F10: Export audit events to syslog/OTel/webhook payload format."""
    require_scope(sess, "admin")
    return await export_audit_events(db, sink=body.sink, after_seq=body.after_seq, limit=body.limit)
