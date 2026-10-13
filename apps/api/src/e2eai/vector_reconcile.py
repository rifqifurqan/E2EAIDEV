"""FR-D9 + FR-R3: retry external vector-store deletes for purges that could not reach the store.

`purge_document` finishes its SQL tightening even when the store is down and records
`vector_store_purge: failed` in the audit log. This admin-only job finds those documents, retries the delete,
and records `vector_store.purge_retry` with a reason code only (`ok` / `failed`) - never error text, hosts or keys.
A document stops being pending once one retry succeeded, so running it twice is harmless.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from . import vector_store as _vs
from .auth import current_session, require_scope
from .db import AuditEntry, User, get_session
from .legal_hold import _require_admin

MAX_PER_RUN = 200


async def _pending_targets(session: AsyncSession, limit: int) -> list[str]:
    failed = (await session.scalars(
        select(AuditEntry.target).where(
            AuditEntry.action == "document.purge",
            AuditEntry.details["vector_store_purge"].astext == "failed",
        ).order_by(AuditEntry.seq)
    )).all()
    recovered = set((await session.scalars(
        select(AuditEntry.target).where(
            AuditEntry.action == "vector_store.purge_retry",
            AuditEntry.details["result"].astext == "ok",
        )
    )).all())
    pending: list[str] = []
    for target in dict.fromkeys(failed):  # oldest first, de-duplicated
        if target not in recovered:
            pending.append(target)
        if len(pending) >= limit:
            break
    return pending


async def reconcile_failed_purges(
    session: AsyncSession, *, actor: User, vector_store: Any = _vs, limit: int = MAX_PER_RUN
) -> dict[str, int]:
    """Retry deletes in the external store for purged documents flagged `failed`. Admin only.

    ``vector_store`` defaults to the configured store (``components.vector_store``); an explicit None, or a
    pgvector install, means there is nothing external to reconcile.
    """
    await _require_admin(session, actor)
    if vector_store is _vs:
        vector_store = _vs.configured_vector_store()
    if vector_store is None:
        return {"retried": 0, "ok": 0, "failed": 0}
    counts = {"retried": 0, "ok": 0, "failed": 0}
    for target in await _pending_targets(session, max(1, min(limit, MAX_PER_RUN))):
        document_id = target.split(":", 1)[1]
        counts["retried"] += 1
        try:
            await vector_store.delete_documents([document_id])
            result = "ok"
        except Exception:  # noqa: BLE001 - any backend failure keeps the document pending
            result = "failed"
        counts[result] += 1
        await audit.record(session, f"user:{actor.id}", "vector_store.purge_retry", target, {"result": result})
    await session.commit()
    return counts


router = APIRouter(prefix="/api/v1/admin/vector-store", tags=["vector-store"])


@router.post("/reconcile-purges")
async def reconcile_purges_api(
    sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)
) -> dict[str, int]:
    require_scope(sess, "admin")
    import uuid

    actor = await db.get(User, uuid.UUID(sess["user_id"]))
    if actor is None:
        from .core.errors import AppError

        raise AppError(401, "Not authenticated")
    return await reconcile_failed_purges(db, actor=actor)
