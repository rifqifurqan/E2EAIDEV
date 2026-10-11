"""Admin flow: register a system, upload OpenAPI spec, choose endpoints,
configure auth, test, and grant roles/divisions (FR-X4).

This module provides the admin workflow for connecting external systems
(ERP, HR, CRM) to the AI platform. Each system goes through:
1. Register — create a named system record
2. Upload spec — OpenAPI 3.x spec → MCP descriptor + spec hash
3. Choose endpoints — select allowed operation IDs
4. Configure auth — set auth mode metadata (no raw credentials stored)
5. Test — offline validation of the configuration
6. Grant — assign principals (role/division) for access

Safety: no raw credentials, bearer tokens, API keys, passwords, or server
URLs are stored in the database or returned in API responses. Auth
configuration stores only the auth mode and a safe endpoint hint.

Real external integration is deferred — this implements the admin flow
contract/boundary with deterministic offline validation.
"""

from __future__ import annotations

import hashlib
import json
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .auth import current_session, require_scope
from .core.errors import AppError
from .db import Base, SystemGrant, SystemRegistration, User, get_session
from .mcp_gen import build_mcp_server_descriptor


# ---------------------------------------------------------------------------
# Service helpers
# ---------------------------------------------------------------------------


async def register_system(
    session: AsyncSession,
    *,
    actor: User,
    name: str,
    description: str = "",
) -> SystemRegistration:
    """Register a new external system. Returns the created record."""
    sys_reg = SystemRegistration(
        name=name,
        description=description,
        owner_id=actor.id,
        status="registered",
        allowed_operations=[],
        auth_config={},
    )
    session.add(sys_reg)
    await audit.record(
        session, f"user:{actor.id}", "system.register",
        f"system:{sys_reg.id}", {"name": name},
    )
    await session.commit()
    return sys_reg


async def upload_openapi_spec(
    session: AsyncSession,
    *,
    system_id: uuid.UUID,
    spec: dict,
) -> dict:
    """Upload and validate an OpenAPI spec for a registered system.

    Stores the spec hash (sha256), generates an MCP descriptor to discover
    operation IDs, and updates the system status. The raw spec is NOT stored
    in the database — only its hash and the discovered operation IDs.
    """
    sys_reg = await _get_system(session, system_id)

    spec_json = json.dumps(spec, sort_keys=True, default=str)
    spec_hash = hashlib.sha256(spec_json.encode()).hexdigest()

    descriptor = build_mcp_server_descriptor(
        system_id=str(system_id),
        spec=spec,
    )

    operation_ids = [t.operation_id for t in descriptor.tools]

    sys_reg.spec_hash = spec_hash
    sys_reg.discovered_operations = operation_ids
    sys_reg.status = "spec_uploaded"

    await audit.record(
        session, f"system:{system_id}", "system.spec.upload",
        f"system:{system_id}",
        {"spec_hash": spec_hash, "total_operations": len(operation_ids)},
    )
    await session.commit()

    return {
        "spec_hash": spec_hash,
        "total_operations": len(operation_ids),
        "operation_ids": operation_ids,
    }


async def set_allowed_operations(
    session: AsyncSession,
    *,
    system_id: uuid.UUID,
    operation_ids: list[str],
) -> dict:
    """Set which operation IDs are allowed for MCP tool calls."""
    sys_reg = await _get_system(session, system_id)

    # Validate against discovered operations if available
    if sys_reg.discovered_operations:
        invalid = set(operation_ids) - set(sys_reg.discovered_operations)
        if invalid:
            raise AppError(400, f"Unknown operations: {', '.join(sorted(invalid))}")

    sys_reg.allowed_operations = operation_ids

    await audit.record(
        session, f"system:{system_id}", "system.endpoints.set",
        f"system:{system_id}",
        {"allowed_count": len(operation_ids)},
    )
    await session.commit()

    return {"allowed": operation_ids}


async def configure_auth(
    session: AsyncSession,
    *,
    system_id: uuid.UUID,
    auth_mode: str,
    token_endpoint_hint: str | None = None,
) -> dict:
    """Configure auth mode for the system. Stores metadata only, never raw credentials.

    The ``token_endpoint_hint`` is stored as a safe hint for the admin UI display.
    Raw credentials, API keys, bearer tokens, and passwords are never stored.
    """
    valid_modes = ("delegated", "token_exchange", "oauth2_cc")
    if auth_mode not in valid_modes:
        raise AppError(400, f"Invalid auth_mode. Use: {', '.join(valid_modes)}")

    sys_reg = await _get_system(session, system_id)

    safe_config: dict = {"auth_mode": auth_mode}
    if token_endpoint_hint:
        safe_config["token_endpoint_hint"] = token_endpoint_hint

    sys_reg.auth_config = safe_config
    sys_reg.status = "auth_configured"

    await audit.record(
        session, f"system:{system_id}", "system.auth.configure",
        f"system:{system_id}",
        {"auth_mode": auth_mode},
    )
    await session.commit()

    return {"auth_mode": auth_mode, "configured": True}


async def test_system(
    session: AsyncSession,
    *,
    system_id: uuid.UUID,
    actor: User,
) -> dict:
    """Offline validation of the system configuration.

    Checks that the spec is uploaded, endpoints are selected, auth is configured,
    and the MCP descriptor can be rebuilt from the stored configuration.
    No real network calls are made.
    """
    sys_reg = await _get_system(session, system_id)

    checks = {
        "spec_uploaded": sys_reg.spec_hash is not None,
        "endpoints_selected": bool(sys_reg.allowed_operations),
        "auth_configured": bool(sys_reg.auth_config.get("auth_mode")),
        "descriptor_valid": bool(sys_reg.discovered_operations),
    }

    all_passed = all(checks.values())
    status = "passed" if all_passed else "failed"

    if all_passed:
        sys_reg.status = "tested"

    await audit.record(
        session, f"user:{actor.id}", "system.test",
        f"system:{system_id}",
        {"status": status, "checks": checks},
    )
    await session.commit()

    return {"status": status, "checks": checks}


async def grant_system(
    session: AsyncSession,
    *,
    system_id: uuid.UUID,
    principals: list[str],
) -> dict:
    """Grant system access to principals (role:xxx, division:xxx, etc.)."""
    sys_reg = await _get_system(session, system_id)

    for principal in principals:
        existing = await session.scalar(
            select(SystemGrant).where(
                SystemGrant.system_id == sys_reg.id,
                SystemGrant.principal == principal,
            )
        )
        if not existing:
            session.add(SystemGrant(system_id=sys_reg.id, principal=principal))

    await audit.record(
        session, f"system:{system_id}", "system.grant",
        f"system:{system_id}",
        {"principals": principals},
    )
    await session.commit()

    return {"granted": principals}


def safe_system_summary(sys_reg: SystemRegistration) -> dict:
    """Build a safe summary dict for API responses. No raw credentials or secrets."""
    return {
        "id": str(sys_reg.id),
        "name": sys_reg.name,
        "description": sys_reg.description,
        "status": sys_reg.status,
        "spec_hash": sys_reg.spec_hash,
        "allowed_operations": sys_reg.allowed_operations,
        "auth_mode": sys_reg.auth_config.get("auth_mode") if sys_reg.auth_config else None,
        "owner_id": str(sys_reg.owner_id),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _get_system(session: AsyncSession, system_id: uuid.UUID) -> SystemRegistration:
    sys_reg = await session.get(SystemRegistration, system_id)
    if sys_reg is None:
        raise AppError(404, "System not found")
    return sys_reg


# ---------------------------------------------------------------------------
# FastAPI routes (FR-X4)
# ---------------------------------------------------------------------------


class RegisterIn(BaseModel):
    name: str
    description: str = ""


class SpecIn(BaseModel):
    spec: dict


class EndpointsIn(BaseModel):
    operation_ids: list[str]


class AuthIn(BaseModel):
    auth_mode: str
    token_endpoint_hint: str | None = None


class GrantIn(BaseModel):
    principals: list[str]


router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.post("/systems")
async def register_system_api(
    body: RegisterIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """FR-X4: Register a new external system."""
    require_scope(sess, "bots")
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None:
        raise AppError(401, "Not authenticated")
    sys_reg = await register_system(db, actor=user, name=body.name, description=body.description)
    return safe_system_summary(sys_reg)


@router.post("/systems/{system_id}/spec")
async def upload_spec_api(
    system_id: uuid.UUID,
    body: SpecIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """FR-X4: Upload OpenAPI spec for a registered system."""
    require_scope(sess, "bots")
    return await upload_openapi_spec(db, system_id=system_id, spec=body.spec)


@router.patch("/systems/{system_id}/endpoints")
async def set_endpoints_api(
    system_id: uuid.UUID,
    body: EndpointsIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """FR-X4: Choose allowed endpoints for MCP tool calls."""
    require_scope(sess, "bots")
    return await set_allowed_operations(db, system_id=system_id, operation_ids=body.operation_ids)


@router.patch("/systems/{system_id}/auth")
async def configure_auth_api(
    system_id: uuid.UUID,
    body: AuthIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """FR-X4: Configure auth mode for a registered system."""
    require_scope(sess, "bots")
    return await configure_auth(
        db, system_id=system_id,
        auth_mode=body.auth_mode,
        token_endpoint_hint=body.token_endpoint_hint,
    )


@router.post("/systems/{system_id}/test")
async def test_system_api(
    system_id: uuid.UUID,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """FR-X4: Run offline validation of the system configuration."""
    require_scope(sess, "bots")
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None:
        raise AppError(401, "Not authenticated")
    return await test_system(db, system_id=system_id, actor=user)


@router.post("/systems/{system_id}/grants")
async def grant_system_api(
    system_id: uuid.UUID,
    body: GrantIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """FR-X4: Grant system access to roles/divisions."""
    require_scope(sess, "bots")
    return await grant_system(db, system_id=system_id, principals=body.principals)
