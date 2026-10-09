"""FR-F12: Scoped API keys for public REST clients (PRD T7).

API clients use `Authorization: Bearer <api key>`. Keys are sha256-hashed before storage;
the raw key is shown only once at creation. Each key carries a list of scopes (chat, documents,
sharing, evals, bots) so access can be narrowed per integration."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .core.errors import AppError
from .db import ApiKey, User, get_session

VALID_SCOPES = frozenset({"chat", "documents", "sharing", "evals", "bots"})
PREFIX_LEN = 12


def hash_api_key(raw: str) -> str:
    """Hash with sha256 — fast lookup by exact match, no salt needed (keys are high-entropy)."""
    return hashlib.sha256(raw.encode()).hexdigest()


def verify_api_key(raw: str, stored_hash: str) -> bool:
    if not raw:
        return False
    return hashlib.sha256(raw.encode()).hexdigest() == stored_hash


def key_prefix(raw: str) -> str:
    return raw[:PREFIX_LEN]


def validate_scopes(scopes: list[str]) -> bool:
    return bool(scopes) and all(s in VALID_SCOPES for s in scopes)


def has_scope(key_scopes: list[str], required: str) -> bool:
    return required in key_scopes


def extract_bearer_token(header: str | None) -> str | None:
    if not header:
        return None
    parts = header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token if token else None


def is_key_usable(*, revoked_at: datetime | None, expires_at: datetime | None) -> bool:
    if revoked_at is not None:
        return False
    if expires_at is not None and expires_at <= datetime.now(UTC):
        return False
    return True


def _generate_raw_key() -> str:
    """Generate a raw API key with an e2eai_ prefix for easy identification."""
    return "e2eai_" + secrets.token_urlsafe(32)


def create_api_key_sync(
    user_id: str,
    name: str,
    scopes: list[str],
    expires_at: datetime | None = None,
) -> dict:
    """Create an API key record (non-DB, synchronous). Returns raw key + metadata.
    This is the pure-logic half; the async DB version calls this then persists."""
    if not validate_scopes(scopes):
        raise ValueError(f"Invalid scopes: {scopes}")
    raw = _generate_raw_key()
    return {
        "raw_key": raw,
        "key_hash": hash_api_key(raw),
        "prefix": key_prefix(raw),
        "name": name,
        "scopes": list(scopes),
        "user_id": user_id,
        "expires_at": expires_at,
    }


# ---------------------------------------------------------------------------
# Async DB service functions
# ---------------------------------------------------------------------------


async def create_api_key(
    session: AsyncSession,
    *,
    user: User,
    name: str,
    scopes: list[str],
    expires_at: datetime | None = None,
) -> dict:
    """Create and persist an API key. Returns the raw key (shown only once)."""
    if not validate_scopes(scopes):
        raise AppError(400, "Invalid scopes", f"Valid scopes: {', '.join(sorted(VALID_SCOPES))}")
    raw = _generate_raw_key()
    key = ApiKey(
        user_id=user.id,
        name=name,
        key_hash=hash_api_key(raw),
        prefix=key_prefix(raw),
        scopes=list(scopes),
        expires_at=expires_at,
    )
    session.add(key)
    await audit.record(session, f"user:{user.id}", "api_key.create", f"api_key:{key.id}",
                       {"name": name, "scopes": list(scopes), "prefix": key_prefix(raw)})
    await session.commit()
    return {
        "id": str(key.id),
        "raw_key": raw,
        "prefix": key_prefix(raw),
        "name": name,
        "scopes": list(scopes),
        "created_at": key.created_at.isoformat() if key.created_at else None,
    }


async def revoke_api_key(
    session: AsyncSession,
    *,
    user: User,
    key_id: uuid.UUID,
) -> None:
    """Revoke an API key (soft delete). Only the key owner can revoke."""
    key = await session.get(ApiKey, key_id)
    if key is None or key.user_id != user.id:
        raise AppError(404, "API key not found")
    if key.revoked_at is not None:
        raise AppError(409, "Already revoked")
    key.revoked_at = datetime.now(UTC)
    await audit.record(session, f"user:{user.id}", "api_key.revoke", f"api_key:{key_id}",
                       {"prefix": key.prefix})
    await session.commit()


async def list_api_keys(
    session: AsyncSession,
    *,
    user: User,
) -> list[dict]:
    """List a user's API keys (without hashes). Shows prefix, name, scopes, status."""
    rows = (await session.execute(
        select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc())
    )).scalars().all()
    return [
        {
            "id": str(k.id),
            "prefix": k.prefix,
            "name": k.name,
            "scopes": k.scopes,
            "expires_at": k.expires_at.isoformat() if k.expires_at else None,
            "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None,
            "created_at": k.created_at.isoformat() if k.created_at else None,
        }
        for k in rows
    ]


async def authenticate_api_key(
    session: AsyncSession,
    raw_key: str,
) -> tuple[User, ApiKey] | None:
    """Look up a raw API key, verify it's usable, and return (user, key) or None."""
    key_hash = hash_api_key(raw_key)
    key = await session.scalar(select(ApiKey).where(ApiKey.key_hash == key_hash))
    if key is None:
        return None
    if not is_key_usable(revoked_at=key.revoked_at, expires_at=key.expires_at):
        return None
    user = await session.get(User, key.user_id)
    if user is None or user.status != "active":
        return None
    return user, key


# ---------------------------------------------------------------------------
# API routes (key management requires a web session, not another API key)
# ---------------------------------------------------------------------------


async def _current_user(db: AsyncSession, sess: dict) -> User:
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None or user.status != "active":
        raise AppError(401, "Not authenticated")
    return user


class ApiKeyCreateIn(BaseModel):
    name: str
    scopes: list[str]
    expires_at: datetime | None = None


def make_router():
    """Build the router lazily so auth imports resolve cleanly."""
    from .auth import current_session

    router = APIRouter(prefix="/api/v1/api-keys", tags=["api-keys"])

    @router.post("")
    async def create_api_key_api(
        body: ApiKeyCreateIn,
        sess: dict = Depends(current_session),
        db: AsyncSession = Depends(get_session),
    ) -> dict:
        user = await _current_user(db, sess)
        return await create_api_key(db, user=user, name=body.name, scopes=body.scopes, expires_at=body.expires_at)

    @router.delete("/{key_id}")
    async def revoke_api_key_api(
        key_id: uuid.UUID,
        sess: dict = Depends(current_session),
        db: AsyncSession = Depends(get_session),
    ) -> dict:
        user = await _current_user(db, sess)
        await revoke_api_key(db, user=user, key_id=key_id)
        return {"status": "revoked"}

    @router.get("")
    async def list_api_keys_api(
        sess: dict = Depends(current_session),
        db: AsyncSession = Depends(get_session),
    ) -> dict:
        user = await _current_user(db, sess)
        return {"keys": await list_api_keys(db, user=user)}

    return router
