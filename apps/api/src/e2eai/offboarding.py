"""User offboarding P0 (US13, FR-F18): deactivate, revoke sessions, transfer ownership, retain chats.

The workflow:
1. Validate: target must be active, admin cannot deactivate self.
2. Set status = 'disabled' → auth.authenticate and authz.principals already reject disabled users.
3. Delete all Valkey sessions for the user (≤ 1 min revocation).
4. Record placeholder revocation for API keys and delegated tokens (those systems aren't built yet).
5. Transfer owned documents and folders to a chosen user (transfer_to_id).
   - Update documents.owner_id + doc_principals (old owner → new owner).
   - Update folders.owner_id.
   - Write OpenFGA tuple changes (delete old owner, write new owner).
   - Existing shares to other users stay intact.
6. Chats are retained (not deleted) — retention policy (NFR-10). The disabled user can no longer
   access them because every auth path checks status='active'.
7. Audit the offboarding action with safe metadata only (no passwords/tokens/session data).
"""

import json
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .auth import current_session, redis_client
from .core.errors import AppError
from .db import DocPrincipal, Document, Folder, User, UserRole, Role, get_session


async def deactivate_user(
    session: AsyncSession,
    redis: Redis,
    authz,
    *,
    admin: User,
    target_user_id: uuid.UUID,
    transfer_to_id: uuid.UUID,
) -> dict:
    """Main offboarding workflow (FR-F18). Returns a summary dict."""
    # ── Validate ──────────────────────────────────────────────────────────
    if admin.id == target_user_id:
        raise AppError(400, "Cannot deactivate yourself")

    target = await session.get(User, target_user_id)
    if target is None:
        raise AppError(404, "User not found")
    if target.status != "active":
        raise AppError(409, "User is already disabled")

    transfer_to = await session.get(User, transfer_to_id)
    if transfer_to is None or transfer_to.status != "active":
        raise AppError(400, "Transfer target must be an active user")

    # ── 1. Disable the user ──────────────────────────────────────────────
    target.status = "disabled"

    # ── 2. Revoke all sessions ───────────────────────────────────────────
    purged_sessions = await _revoke_all_sessions(redis, str(target_user_id))

    # ── 3. Placeholder: revoke API keys and delegated tokens ─────────────
    await audit.record(session, f"user:{admin.id}", "user.api_keys.revoked",
                       f"user:{target_user_id}", {"count": 0, "placeholder": True})
    await audit.record(session, f"user:{admin.id}", "user.delegated_tokens.revoked",
                       f"user:{target_user_id}", {"count": 0, "placeholder": True})

    # ── 4. Transfer document ownership ───────────────────────────────────
    docs_transferred = await _transfer_documents(session, authz, source_id=target_user_id, dest_id=transfer_to_id)

    # ── 5. Transfer folder ownership ─────────────────────────────────────
    folders_transferred = await _transfer_folders(session, source_id=target_user_id, dest_id=transfer_to_id)

    # ── 6. Audit the offboarding ─────────────────────────────────────────
    await audit.record(session, f"user:{admin.id}", "user.offboard", f"user:{target_user_id}", {
        "transfer_to": str(transfer_to_id),
        "documents_transferred": docs_transferred,
        "folders_transferred": folders_transferred,
        "sessions_purged": purged_sessions,
    })
    await session.commit()

    return {
        "status": "disabled",
        "documents_transferred": docs_transferred,
        "folders_transferred": folders_transferred,
        "sessions_purged": purged_sessions,
    }


async def _revoke_all_sessions(redis: Redis, user_id: str) -> int:
    """Delete every Valkey session belonging to this user. Uses SCAN (P0 scale is tiny)."""
    count = 0
    cursor = 0
    while True:
        cursor, keys = await redis.scan(cursor, match="sess:*", count=200)
        for key in keys:
            raw = await redis.get(key)
            if raw is not None:
                try:
                    data = json.loads(raw)
                    if data.get("user_id") == user_id:
                        await redis.delete(key)
                        count += 1
                except (json.JSONDecodeError, TypeError):
                    pass
        if cursor == 0:
            break
    return count


async def _transfer_documents(
    session: AsyncSession, authz, *, source_id: uuid.UUID, dest_id: uuid.UUID
) -> int:
    """Transfer all documents owned by source_id to dest_id. Existing shares stay intact."""
    docs = list(await session.scalars(
        select(Document).where(Document.owner_id == source_id, Document.status != "purged")
    ))
    if not docs:
        return 0

    authz_writes = []
    authz_deletes = []

    for doc in docs:
        doc.owner_id = dest_id

        # Update doc_principals: remove old owner, add new owner
        old_principal = await session.scalar(
            select(DocPrincipal).where(
                DocPrincipal.document_id == doc.id,
                DocPrincipal.principal == f"user:{source_id}",
                DocPrincipal.level == "owner",
            )
        )
        if old_principal:
            await session.delete(old_principal)
            authz_deletes.append({
                "user": f"user:{source_id}",
                "relation": "owner",
                "object": f"document:{doc.id}",
            })

        # Merge new owner principal (if dest already has a non-owner share, upgrade to owner)
        await session.merge(DocPrincipal(document_id=doc.id, principal=f"user:{dest_id}", level="owner"))
        authz_writes.append({
            "user": f"user:{dest_id}",
            "relation": "owner",
            "object": f"document:{doc.id}",
        })

    await session.flush()

    # Write OpenFGA tuple changes
    if authz_deletes or authz_writes:
        await authz.write(writes=authz_writes, deletes=authz_deletes)

    return len(docs)


async def _transfer_folders(
    session: AsyncSession, *, source_id: uuid.UUID, dest_id: uuid.UUID
) -> int:
    """Transfer all folders owned by source_id to dest_id."""
    result = await session.execute(
        update(Folder).where(Folder.owner_id == source_id).values(owner_id=dest_id)
    )
    await session.flush()
    return result.rowcount


# ---------------------------------------------------------------------------
# API route (PRD T7: Admin → Org)
# ---------------------------------------------------------------------------

async def _require_admin(db: AsyncSession, sess: dict) -> User:
    """Load the current user and verify they have the admin role."""
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None or user.status != "active":
        raise AppError(401, "Not authenticated")
    admin_role = await db.scalar(select(Role).where(Role.name == "admin"))
    if admin_role is None:
        raise AppError(403, "Not allowed")
    has_role = await db.scalar(
        select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == admin_role.id)
    )
    if has_role is None:
        raise AppError(403, "Not allowed")
    return user


class DeactivateIn(BaseModel):
    transfer_to_id: uuid.UUID


router = APIRouter(prefix="/api/v1", tags=["admin"])


@router.post("/users/{user_id}/deactivate")
async def deactivate_user_api(
    user_id: uuid.UUID,
    body: DeactivateIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Deactivate a user and transfer their assets (FR-F18, US13). Requires admin role."""
    from .authz import connect
    from .core.config import get_settings

    admin = await _require_admin(db, sess)
    authz = await connect(get_settings(), db)
    return await deactivate_user(
        db, redis_client(), authz,
        admin=admin, target_user_id=user_id, transfer_to_id=body.transfer_to_id,
    )
