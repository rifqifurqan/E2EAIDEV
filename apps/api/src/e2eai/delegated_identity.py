"""Delegated identity / token exchange boundary for MCP tool calls (FR-X3).

AI calls system APIs with the asking user's identity (OAuth token exchange or
per-user delegated token). A super-admin service account is NEVER used for
user data.

This module provides:
- ``AuthMode`` enum: DELEGATED, TOKEN_EXCHANGE, SERVICE_ACCOUNT
- ``DelegatedIdentityContext``: safe metadata (user_id, system_id, auth_mode)
  — never stores raw tokens, bearer values, passwords, or secrets
- ``validate_identity_for_user_data``: fails closed if identity is SERVICE_ACCOUNT
  or user_id is missing
- ``safe_audit_metadata``: builds audit-safe metadata dict from a context
- ``DelegatedExecutor``: wraps an Executor, validates identity before each call,
  and injects identity metadata into results
- API route for validating a delegated identity context

Real external OAuth provider integration is deferred — this module implements
the offline contract/boundary so the rest of the system can enforce identity
requirements deterministically.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import current_session, require_scope
from .db import get_session
from .mcp_tool_call import Executor, MCPToolCallRecord


# ---------------------------------------------------------------------------
# Auth mode enum
# ---------------------------------------------------------------------------


class AuthMode(str, enum.Enum):
    """How the AI authenticates to a system API on behalf of a user.

    DELEGATED: per-user delegated credential (API key, session cookie, etc.)
    TOKEN_EXCHANGE: OAuth 2.0 token exchange (RFC 8693) — user token → scoped token
    SERVICE_ACCOUNT: system-wide admin credential — NEVER allowed for user data
    """
    DELEGATED = "delegated"
    TOKEN_EXCHANGE = "token_exchange"
    SERVICE_ACCOUNT = "service_account"


# ---------------------------------------------------------------------------
# Identity context (safe metadata only — no raw tokens)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DelegatedIdentityContext:
    """Per-request identity context for MCP tool execution.

    Carries only safe metadata: user_id, system_id, auth_mode.
    NEVER stores raw tokens, bearer values, passwords, API keys, or secrets.
    """
    user_id: str
    system_id: str
    auth_mode: AuthMode


# ---------------------------------------------------------------------------
# Validation: fail closed for SERVICE_ACCOUNT or missing user
# ---------------------------------------------------------------------------


def validate_identity_for_user_data(ctx: DelegatedIdentityContext) -> None:
    """Validate that the identity context is safe for accessing user data.

    Raises ValueError if:
    - auth_mode is SERVICE_ACCOUNT (never allowed for user data)
    - user_id is empty/missing (identity is incomplete)
    """
    if ctx.auth_mode == AuthMode.SERVICE_ACCOUNT:
        raise ValueError(
            "Service account is not allowed for user-data calls. "
            "Delegated identity (token exchange or per-user delegation) is required. "
            "FR-X3: AI must act as the real user, never as a super-admin."
        )
    if not ctx.user_id or not ctx.user_id.strip():
        raise ValueError(
            "User id is required in the delegated identity context. "
            "Identity missing: cannot execute MCP tool call without a bound user."
        )


# ---------------------------------------------------------------------------
# Safe audit metadata builder
# ---------------------------------------------------------------------------


def safe_audit_metadata(ctx: DelegatedIdentityContext) -> dict:
    """Build a safe audit metadata dict from a DelegatedIdentityContext.

    Contains only acting_user_id, system_id, auth_mode — never raw tokens,
    bearer values, passwords, API keys, or secrets.
    """
    return {
        "acting_user_id": ctx.user_id,
        "system_id": ctx.system_id,
        "auth_mode": ctx.auth_mode.value,
    }


# ---------------------------------------------------------------------------
# DelegatedExecutor: wraps an Executor, validates identity before each call
# ---------------------------------------------------------------------------


class DelegatedExecutor:
    """Executor wrapper that enforces delegated identity (FR-X3).

    Validates the identity context before each tool call. Rejects SERVICE_ACCOUNT.
    Passes through to the inner executor for valid identities.
    """

    def __init__(self, *, inner: Executor, identity: DelegatedIdentityContext) -> None:
        self._inner = inner
        self._identity = identity

    @property
    def identity(self) -> DelegatedIdentityContext:
        return self._identity

    async def execute(self, record: MCPToolCallRecord) -> dict:
        """Execute after validating identity. Raises ValueError for SERVICE_ACCOUNT."""
        validate_identity_for_user_data(self._identity)
        return await self._inner.execute(record)


# ---------------------------------------------------------------------------
# FastAPI route: validate delegated identity context
# ---------------------------------------------------------------------------


class DelegatedIdentityValidateIn(BaseModel):
    user_id: str
    auth_mode: str  # "delegated" | "token_exchange" | "service_account"


router = APIRouter(prefix="/api/v1", tags=["systems"])


@router.post("/systems/{system_id}/delegated-identity/validate")
async def validate_delegated_identity_api(
    system_id: str,
    body: DelegatedIdentityValidateIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """FR-X3: Validate a delegated identity context for a system.

    Returns validation result. Rejects SERVICE_ACCOUNT for user-data access.
    Never returns raw tokens, bearer values, API keys, or secrets.
    """
    require_scope(sess, "bots")

    try:
        mode = AuthMode(body.auth_mode)
    except ValueError:
        return {
            "valid": False,
            "error": f"Unknown auth_mode: {body.auth_mode}. Use: delegated, token_exchange, service_account.",
        }

    ctx = DelegatedIdentityContext(
        user_id=body.user_id,
        system_id=system_id,
        auth_mode=mode,
    )

    try:
        validate_identity_for_user_data(ctx)
    except ValueError as exc:
        return {"valid": False, "error": str(exc)}

    return {
        "valid": True,
        "acting_user_id": ctx.user_id,
        "system_id": ctx.system_id,
        "auth_mode": ctx.auth_mode.value,
    }
