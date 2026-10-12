"""Secret and certificate rotation (FR-F17).

- API keys rotate with an overlap (grace) window so clients switch without downtime.
- A leaked key can be revoked immediately (well inside the 5 minute requirement).
- Generated secrets follow the project charset rules ([A-Za-z0-9._~-], >= 16 chars).
- Certificates report an `expiring` state 14 days before expiry.
- Rotation plans describe steps only; they never contain secret values.
- Audit events store only key ids/prefixes, never raw keys.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .api_keys import _generate_raw_key, hash_api_key, key_prefix
from .auth import current_session, require_scope
from .core.errors import AppError
from .db import ApiKey, User, get_session

SECRET_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._~-"
MIN_SECRET_LENGTH = 16
CERT_WARN_DAYS = 14
MAX_GRACE_MINUTES = 24 * 60

# Secrets known to the platform and how each is rotated without downtime.
ROTATABLE_SECRETS: dict[str, dict[str, str]] = {
    "litellm_master_key": {
        "strategy": "dual-key-overlap",
        "steps": "issue new virtual/master key; update api+worker env; keep old key until traffic drains; revoke old key",
    },
    "api_keys": {
        "strategy": "dual-key-overlap",
        "steps": "POST rotate (new key issued, old key expires after grace); clients switch; old key stops working",
    },
    "oidc_client_secret": {
        "strategy": "dual-key-overlap",
        "steps": "add second client secret at the IdP; deploy new secret; remove the old secret",
    },
    "db_password": {
        "strategy": "dual-credential-overlap",
        "steps": "create second DB role with same grants; switch DSN; drop the old role after connections drain",
    },
    "valkey_password": {
        "strategy": "dual-credential-overlap",
        "steps": "add a second ACL user; switch api+worker; delete the old ACL user",
    },
    "s3_access_key": {
        "strategy": "dual-credential-overlap",
        "steps": "create a second S3 identity; switch config; delete the old identity",
    },
}


def generate_secret(length: int = 32) -> str:
    """Generate a secret using only [A-Za-z0-9._~-] (safe in DSNs, .env, and SQL)."""
    if length < MIN_SECRET_LENGTH:
        raise ValueError(f"Secrets must be at least {MIN_SECRET_LENGTH} characters")
    return "".join(secrets.choice(SECRET_ALPHABET) for _ in range(length))


def certificate_status(not_after: datetime, *, now: datetime | None = None) -> dict[str, Any]:
    """Classify a certificate by expiry; warns CERT_WARN_DAYS before it expires."""
    current = now or datetime.now(UTC)
    if not_after.tzinfo is None:
        not_after = not_after.replace(tzinfo=UTC)
    delta = not_after - current
    days_left = delta.days if delta >= timedelta(0) else -((-delta).days + (1 if (-delta).seconds else 0))
    if delta < timedelta(0):
        state = "expired"
    elif delta <= timedelta(days=CERT_WARN_DAYS):
        state = "expiring"
    else:
        state = "ok"
    return {
        "state": state,
        "days_left": days_left,
        "not_after": not_after.isoformat(),
        "warn_days": CERT_WARN_DAYS,
    }


def build_rotation_plan(secret_names: list[str]) -> dict[str, Any]:
    """Return zero-downtime rotation steps for the named secrets (no secret values)."""
    steps = []
    for name in secret_names:
        spec = ROTATABLE_SECRETS.get(name)
        if spec is None:
            raise ValueError(f"Unknown secret: {name}")
        steps.append({"secret": name, "strategy": spec["strategy"], "steps": spec["steps"].split("; ")})
    return {"steps": steps, "downtime": "none", "emergency_revoke_target_minutes": 5}


async def rotate_api_key(
    session: AsyncSession,
    *,
    user: User,
    key_id: str | uuid.UUID,
    grace_minutes: int = 10,
) -> dict[str, Any]:
    """Issue a replacement key (same name/scopes) and let the old key expire after a grace window."""
    kid = uuid.UUID(str(key_id))
    old = await session.get(ApiKey, kid)
    if old is None or old.user_id != user.id:
        raise AppError(404, "API key not found")
    if old.revoked_at is not None:
        raise AppError(409, "API key is revoked")
    grace = max(0, min(int(grace_minutes), MAX_GRACE_MINUTES))
    now = datetime.now(UTC)
    old_expiry = now + timedelta(minutes=grace)
    if old.expires_at is None or old.expires_at > old_expiry:
        old.expires_at = old_expiry
    raw = _generate_raw_key()
    new = ApiKey(
        user_id=user.id,
        name=old.name,
        key_hash=hash_api_key(raw),
        prefix=key_prefix(raw),
        scopes=list(old.scopes or []),
    )
    session.add(new)
    await session.flush()
    await audit.record(
        session,
        f"user:{user.id}",
        "secret.api_key.rotate",
        f"api_key:{old.id}",
        {"old_prefix": old.prefix, "new_prefix": new.prefix, "new_key_id": str(new.id), "grace_minutes": grace},
    )
    await session.commit()
    return {
        "id": str(new.id),
        "raw_key": raw,
        "prefix": new.prefix,
        "name": new.name,
        "scopes": list(new.scopes),
        "old_key_id": str(old.id),
        "old_key_expires_at": old.expires_at.isoformat(),
    }


async def emergency_revoke_api_key(
    session: AsyncSession,
    *,
    actor_id: str,
    key_id: str | uuid.UUID,
    reason: str = "",
) -> dict[str, Any]:
    """Immediately revoke a (leaked) API key; effective on the very next authentication."""
    key = await session.get(ApiKey, uuid.UUID(str(key_id)))
    if key is None:
        raise AppError(404, "API key not found")
    if key.revoked_at is None:
        key.revoked_at = datetime.now(UTC)
    await audit.record(
        session,
        actor_id,
        "secret.api_key.emergency_revoke",
        f"api_key:{key.id}",
        {"prefix": key.prefix, "reason_given": bool(reason)},
    )
    await session.commit()
    return {"status": "revoked", "key_id": str(key.id), "prefix": key.prefix}


class RotateIn(BaseModel):
    grace_minutes: int = 10


class EmergencyRevokeIn(BaseModel):
    reason: str = ""


class CertificateStatusIn(BaseModel):
    not_after: datetime


class RotationPlanIn(BaseModel):
    secrets: list[str]


router = APIRouter(prefix="/api/v1/security", tags=["security"])


async def _user(db: AsyncSession, sess: dict) -> User:
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None or user.status != "active":
        raise AppError(401, "Not authenticated")
    return user


@router.post("/api-keys/{key_id}/rotate")
async def rotate_api_key_api(
    key_id: uuid.UUID,
    body: RotateIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """FR-F17: rotate one of the caller's API keys with an overlap window."""
    user = await _user(db, sess)
    return await rotate_api_key(db, user=user, key_id=key_id, grace_minutes=body.grace_minutes)


@router.post("/api-keys/{key_id}/emergency-revoke")
async def emergency_revoke_api_key_api(
    key_id: uuid.UUID,
    body: EmergencyRevokeIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """FR-F17: admin emergency revocation of a leaked key."""
    require_scope(sess, "admin")
    user = await _user(db, sess)
    return await emergency_revoke_api_key(db, actor_id=f"user:{user.id}", key_id=key_id, reason=body.reason)


@router.post("/certificate-status")
async def certificate_status_api(body: CertificateStatusIn, sess: dict = Depends(current_session)) -> dict[str, Any]:
    """FR-F17: report certificate expiry state (warns 14 days before)."""
    require_scope(sess, "admin")
    return certificate_status(body.not_after)


@router.post("/rotation-plan")
async def rotation_plan_api(body: RotationPlanIn, sess: dict = Depends(current_session)) -> dict[str, Any]:
    """FR-F17: zero-downtime rotation steps (no secret values)."""
    require_scope(sess, "admin")
    try:
        return build_rotation_plan(body.secrets)
    except ValueError as exc:
        raise AppError(400, str(exc)) from exc
