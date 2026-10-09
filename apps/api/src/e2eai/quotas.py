"""Rate limits and quotas per user, team, and division (FR-F13, FR-F15, NFR-19).

Policy resolution: user > team > division > org default > built-in default.
Enforcement is fail-closed: if the quota store (Valkey) is unreachable, the request is denied.

Dimensions:
- request count window (per minute, using Valkey fixed-window counters)
- token budget (per day, estimated from prompt+answer text length)
- storage bytes (per user, summed from document_versions.size)

Returns 429 for request/token limits, 413 for storage quota, with RFC 9457 problem details
consistent with the existing AppError pattern.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from .core.errors import AppError
from .core.ids import uuid7
from .db import Base, DocumentVersion, TeamMember, User

log = logging.getLogger("e2eai.quotas")

# ---------------------------------------------------------------------------
# Built-in defaults (FR-F15: 20 GB storage, sensible request/token limits)
# ---------------------------------------------------------------------------

DEFAULT_REQUESTS_PER_MINUTE = 60
DEFAULT_TOKENS_PER_DAY = 500_000
DEFAULT_STORAGE_BYTES = 20 * 1024**3  # 20 GB

SCOPE_PRIORITY = {"user": 0, "team": 1, "division": 2, "org": 3}


# ---------------------------------------------------------------------------
# QuotaPolicy: in-memory resolved policy
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class QuotaPolicy:
    scope: str
    scope_id: str
    requests_per_minute: int
    tokens_per_day: int
    storage_bytes: int


def _builtin_default() -> QuotaPolicy:
    return QuotaPolicy(
        scope="default", scope_id="builtin",
        requests_per_minute=DEFAULT_REQUESTS_PER_MINUTE,
        tokens_per_day=DEFAULT_TOKENS_PER_DAY,
        storage_bytes=DEFAULT_STORAGE_BYTES,
    )


def resolve_policy(policies: list[QuotaPolicy]) -> QuotaPolicy:
    """Pick the most specific policy: user > team > division > org > built-in default."""
    if not policies:
        return _builtin_default()
    policies_sorted = sorted(policies, key=lambda p: SCOPE_PRIORITY.get(p.scope, 99))
    return policies_sorted[0]


# ---------------------------------------------------------------------------
# ORM model: quota_policies table
# ---------------------------------------------------------------------------

class QuotaPolicyRow(Base):
    """FR-F13: admin-configurable quota policy per scope dimension."""
    __tablename__ = "quota_policies"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    scope: Mapped[str] = mapped_column(String(16))  # user/team/division/org
    scope_id: Mapped[str] = mapped_column(String(80))  # uuid of the entity
    requests_per_minute: Mapped[int] = mapped_column(Integer, default=DEFAULT_REQUESTS_PER_MINUTE)
    tokens_per_day: Mapped[int] = mapped_column(Integer, default=DEFAULT_TOKENS_PER_DAY)
    storage_bytes: Mapped[int] = mapped_column(BigInteger, default=DEFAULT_STORAGE_BYTES)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ---------------------------------------------------------------------------
# Policy CRUD
# ---------------------------------------------------------------------------

async def upsert_quota_policy(
    session: AsyncSession,
    *,
    scope: str,
    scope_id: str,
    requests_per_minute: int | None = None,
    tokens_per_day: int | None = None,
    storage_bytes: int | None = None,
) -> QuotaPolicyRow:
    """Create or update a quota policy for a scope dimension."""
    existing = await session.scalar(
        select(QuotaPolicyRow).where(
            QuotaPolicyRow.scope == scope,
            QuotaPolicyRow.scope_id == scope_id,
        )
    )
    if existing:
        if requests_per_minute is not None:
            existing.requests_per_minute = requests_per_minute
        if tokens_per_day is not None:
            existing.tokens_per_day = tokens_per_day
        if storage_bytes is not None:
            existing.storage_bytes = storage_bytes
        await session.commit()
        return existing
    row = QuotaPolicyRow(
        scope=scope,
        scope_id=scope_id,
        requests_per_minute=requests_per_minute or DEFAULT_REQUESTS_PER_MINUTE,
        tokens_per_day=tokens_per_day or DEFAULT_TOKENS_PER_DAY,
        storage_bytes=storage_bytes or DEFAULT_STORAGE_BYTES,
    )
    session.add(row)
    await session.commit()
    return row


async def get_effective_policy(session: AsyncSession, *, user: User) -> QuotaPolicy:
    """Resolve the effective quota policy for a user by checking user > team > division > org."""
    candidates: list[QuotaPolicy] = []

    # User-level policy
    user_row = await session.scalar(
        select(QuotaPolicyRow).where(
            QuotaPolicyRow.scope == "user",
            QuotaPolicyRow.scope_id == str(user.id),
        )
    )
    if user_row:
        candidates.append(QuotaPolicy(
            scope="user", scope_id=str(user.id),
            requests_per_minute=user_row.requests_per_minute,
            tokens_per_day=user_row.tokens_per_day,
            storage_bytes=user_row.storage_bytes,
        ))

    # Team-level policies
    team_ids = list(await session.scalars(
        select(TeamMember.team_id).where(TeamMember.user_id == user.id)
    ))
    for team_id in team_ids:
        team_row = await session.scalar(
            select(QuotaPolicyRow).where(
                QuotaPolicyRow.scope == "team",
                QuotaPolicyRow.scope_id == str(team_id),
            )
        )
        if team_row:
            candidates.append(QuotaPolicy(
                scope="team", scope_id=str(team_id),
                requests_per_minute=team_row.requests_per_minute,
                tokens_per_day=team_row.tokens_per_day,
                storage_bytes=team_row.storage_bytes,
            ))

    # Division-level policy
    if user.division_id:
        div_row = await session.scalar(
            select(QuotaPolicyRow).where(
                QuotaPolicyRow.scope == "division",
                QuotaPolicyRow.scope_id == str(user.division_id),
            )
        )
        if div_row:
            candidates.append(QuotaPolicy(
                scope="division", scope_id=str(user.division_id),
                requests_per_minute=div_row.requests_per_minute,
                tokens_per_day=div_row.tokens_per_day,
                storage_bytes=div_row.storage_bytes,
            ))

    # Org-level policy
    org_row = await session.scalar(
        select(QuotaPolicyRow).where(
            QuotaPolicyRow.scope == "org",
            QuotaPolicyRow.scope_id == str(user.org_id),
        )
    )
    if org_row:
        candidates.append(QuotaPolicy(
            scope="org", scope_id=str(user.org_id),
            requests_per_minute=org_row.requests_per_minute,
            tokens_per_day=org_row.tokens_per_day,
            storage_bytes=org_row.storage_bytes,
        ))

    return resolve_policy(candidates)


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~1 token per 4 characters. Acceptable for P1 accounting."""
    if not text:
        return 0
    return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# Valkey-backed rate-limit and token-budget checks
# ---------------------------------------------------------------------------

async def check_request_rate(redis, *, user_id: str, endpoint: str, policy: QuotaPolicy) -> tuple[bool, dict]:
    """Fixed-window request rate limit in Valkey. Fail-closed on errors (NFR-19)."""
    window = 60  # 1 minute
    bucket = f"quota:req:{user_id}:{endpoint}"
    try:
        count = await redis.incr(bucket)
        if count == 1:
            await redis.expire(bucket, window)
        if count > policy.requests_per_minute:
            ttl_raw = await redis.get(bucket)  # bucket exists; get TTL info from expires
            return False, {"reason": "Rate limit exceeded", "retry_after": window, "limit": policy.requests_per_minute}
        return True, {}
    except Exception as e:
        log.warning("quota check failed closed (request rate): %s", e)
        return False, {"reason": "Quota service unavailable — request denied (fail-closed)"}


async def check_token_budget(redis, *, user_id: str, estimated_tokens: int, policy: QuotaPolicy) -> tuple[bool, dict]:
    """Daily token budget check in Valkey. Fail-closed on errors (NFR-19)."""
    bucket = f"quota:tok:{user_id}"
    try:
        raw = await redis.get(bucket)
        used = int(raw) if raw else 0
        if used + estimated_tokens > policy.tokens_per_day:
            return False, {"reason": "Token budget exceeded", "used": used, "limit": policy.tokens_per_day}
        return True, {}
    except Exception as e:
        log.warning("quota check failed closed (token budget): %s", e)
        return False, {"reason": "Quota service unavailable — request denied (fail-closed)"}


async def record_token_usage(redis, *, user_id: str, tokens: int) -> None:
    """Record token usage. Best-effort — a failed write does not block the response."""
    bucket = f"quota:tok:{user_id}"
    try:
        count = await redis.incrby(bucket, tokens)
        if count == tokens:
            # First write today — set a 24h TTL
            await redis.expire(bucket, 86400)
    except Exception as e:
        log.warning("failed to record token usage: %s", e)


# ---------------------------------------------------------------------------
# Storage quota check (DB-backed)
# ---------------------------------------------------------------------------

async def check_storage_quota(
    session: AsyncSession, *, user_id: uuid.UUID, upload_bytes: int, policy: QuotaPolicy
) -> tuple[bool, dict]:
    """Check if the user's total storage + upload_bytes exceeds their quota."""
    from .db import Document
    used = await session.scalar(
        select(func.coalesce(func.sum(DocumentVersion.size), 0))
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(Document.owner_id == user_id)
    ) or 0
    if used + upload_bytes > policy.storage_bytes:
        return False, {
            "reason": "Storage quota exceeded",
            "used": used,
            "limit": policy.storage_bytes,
            "upload_bytes": upload_bytes,
        }
    return True, {}


# ---------------------------------------------------------------------------
# Enforcement helpers: raise AppError if over quota
# ---------------------------------------------------------------------------

async def enforce_request_quota(redis, *, user_id: str, endpoint: str, policy: QuotaPolicy) -> None:
    """Raise 429 if the request rate limit is exceeded."""
    allowed, info = await check_request_rate(redis, user_id=user_id, endpoint=endpoint, policy=policy)
    if not allowed:
        raise AppError(
            429, "Rate limit exceeded",
            info.get("reason", "Too many requests. Please wait and try again."),
        )


async def enforce_token_quota(redis, *, user_id: str, estimated_tokens: int, policy: QuotaPolicy) -> None:
    """Raise 429 if the token budget is exceeded."""
    allowed, info = await check_token_budget(redis, user_id=user_id, estimated_tokens=estimated_tokens, policy=policy)
    if not allowed:
        raise AppError(
            429, "Token quota exceeded",
            info.get("reason", "Daily token budget exceeded. Please wait until tomorrow."),
        )


async def enforce_storage_quota(session: AsyncSession, *, user_id: uuid.UUID, upload_bytes: int, policy: QuotaPolicy) -> None:
    """Raise 413 if storage quota would be exceeded by the upload."""
    allowed, info = await check_storage_quota(session, user_id=user_id, upload_bytes=upload_bytes, policy=policy)
    if not allowed:
        raise AppError(
            413, "Storage quota exceeded",
            info.get("reason", "Storage quota exceeded. Delete old files or contact your admin."),
        )
