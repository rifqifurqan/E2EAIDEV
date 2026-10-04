"""Hash-chained audit log (FR-F9, NFR-11): each row stores sha256(prev_hash + row), so editing or
deleting any row breaks every hash after it."""

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .db import AuditEntry

GENESIS = "0" * 64
_LOCK = 0x45324541  # advisory lock id: one writer at a time keeps the chain linear


def _digest(prev_hash: str, at: datetime, actor: str, action: str, target: str, details: dict) -> str:
    payload = json.dumps([prev_hash, at.isoformat(), actor, action, target, details], sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


async def record(session: AsyncSession, actor: str, action: str, target: str, details: dict | None = None) -> None:
    """Append one entry inside the caller's transaction (commits with the change it describes)."""
    details = details or {}
    await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK})
    prev = await session.scalar(select(AuditEntry.hash).order_by(AuditEntry.seq.desc()).limit(1)) or GENESIS
    at = datetime.now(UTC)
    session.add(AuditEntry(at=at, actor=actor, action=action, target=target, details=details,
                           prev_hash=prev, hash=_digest(prev, at, actor, action, target, details)))
    await session.flush()


async def verify_chain(session: AsyncSession) -> int | None:
    """Return the seq of the first broken entry, or None if the whole chain is intact."""
    prev = GENESIS
    for e in await session.scalars(select(AuditEntry).order_by(AuditEntry.seq)):
        if e.prev_hash != prev or e.hash != _digest(prev, e.at, e.actor, e.action, e.target, e.details):
            return e.seq
        prev = e.hash
    return None
