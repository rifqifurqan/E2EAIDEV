"""FR-X4 Admin flow: register a system, upload OpenAPI spec, choose endpoints,
configure auth, test, and grant roles/divisions.

Tests verify:
- System registration creates a safe DB record (no raw secrets)
- OpenAPI spec upload generates MCP descriptor and stores spec hash (no raw spec in output)
- Endpoint selection stores allowed operation IDs
- Auth configuration stores auth mode metadata only (no raw credentials)
- Playground test validates descriptor + identity offline
- Grant assigns principals (role/division) to the system
- Safe output: no raw secrets, tokens, credentials, or server URLs in any API response
- Route wiring in the FastAPI app
"""

import pytest


# ---------------------------------------------------------------------------
# Unit tests: SystemRegistration model and service
# ---------------------------------------------------------------------------


def test_register_system_creates_record():
    """Admin can register a new external system with name and description."""
    import asyncio
    import subprocess

    from sqlalchemy import delete, func, select

    async def run():
        from e2eai.db import User, sessions
        from e2eai.seed import seed_demo
        from e2eai.system_registration import SystemRegistration, register_system

        async with sessions()() as session:
            await session.execute(delete(SystemRegistration))
            await session.commit()
            await seed_demo(session, password="TestPassword_123456789")
            admin = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))

            sys_reg = await register_system(
                session, actor=admin,
                name="HR System",
                description="Corporate HR API",
            )
            assert sys_reg.id is not None
            assert sys_reg.name == "HR System"
            assert sys_reg.description == "Corporate HR API"
            assert sys_reg.owner_id == admin.id
            assert sys_reg.status == "registered"
            assert sys_reg.allowed_operations == []
            assert sys_reg.auth_config == {}

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
    asyncio.run(run())


def test_upload_openapi_spec_generates_descriptor():
    """Uploading an OpenAPI spec generates an MCP descriptor and stores the spec hash."""
    import asyncio
    import subprocess

    from sqlalchemy import delete, func, select

    async def run():
        from e2eai.db import User, sessions
        from e2eai.seed import seed_demo
        from e2eai.system_registration import SystemRegistration, register_system, upload_openapi_spec

        async with sessions()() as session:
            await session.execute(delete(SystemRegistration))
            await session.commit()
            await seed_demo(session, password="TestPassword_123456789")
            admin = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))

            sys_reg = await register_system(session, actor=admin, name="HR API", description="HR")

            spec = {
                "openapi": "3.0.0",
                "info": {"title": "HR API", "version": "1.0.0"},
                "paths": {
                    "/employees": {
                        "get": {
                            "operationId": "list_employees",
                            "summary": "List employees",
                            "responses": {"200": {"description": "OK"}},
                        },
                    },
                    "/employees/{id}": {
                        "get": {
                            "operationId": "get_employee",
                            "summary": "Get employee by ID",
                            "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}],
                            "responses": {"200": {"description": "OK"}},
                        },
                    },
                },
            }

            result = await upload_openapi_spec(session, system_id=sys_reg.id, spec=spec)
            assert result["spec_hash"] is not None
            assert len(result["spec_hash"]) == 64  # sha256 hex
            assert result["total_operations"] >= 2
            assert result["operation_ids"]  # list of discovered operation IDs

            await session.refresh(sys_reg)
            assert sys_reg.spec_hash is not None
            assert sys_reg.status == "spec_uploaded"

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
    asyncio.run(run())


def test_choose_allowed_endpoints():
    """Admin can choose which operation IDs are allowed for MCP tool calls."""
    import asyncio
    import subprocess

    from sqlalchemy import delete, func, select

    async def run():
        from e2eai.db import User, sessions
        from e2eai.seed import seed_demo
        from e2eai.system_registration import (
            SystemRegistration, register_system, upload_openapi_spec, set_allowed_operations,
        )

        async with sessions()() as session:
            await session.execute(delete(SystemRegistration))
            await session.commit()
            await seed_demo(session, password="TestPassword_123456789")
            admin = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))

            sys_reg = await register_system(session, actor=admin, name="HR API", description="HR")
            spec = {
                "openapi": "3.0.0",
                "info": {"title": "HR API", "version": "1.0.0"},
                "paths": {
                    "/employees": {
                        "get": {"operationId": "list_employees", "summary": "List", "responses": {"200": {"description": "OK"}}},
                        "post": {"operationId": "create_employee", "summary": "Create", "responses": {"201": {"description": "Created"}}},
                    },
                },
            }
            await upload_openapi_spec(session, system_id=sys_reg.id, spec=spec)

            result = await set_allowed_operations(
                session, system_id=sys_reg.id,
                operation_ids=["list_employees"],  # only allow read
            )
            assert result["allowed"] == ["list_employees"]
            assert "create_employee" not in result["allowed"]

            await session.refresh(sys_reg)
            assert sys_reg.allowed_operations == ["list_employees"]

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
    asyncio.run(run())


def test_configure_auth_stores_mode_only():
    """Auth configuration stores mode metadata, never raw credentials."""
    import asyncio
    import subprocess

    from sqlalchemy import delete, func, select

    async def run():
        from e2eai.db import User, sessions
        from e2eai.seed import seed_demo
        from e2eai.system_registration import (
            SystemRegistration, register_system, configure_auth,
        )

        async with sessions()() as session:
            await session.execute(delete(SystemRegistration))
            await session.commit()
            await seed_demo(session, password="TestPassword_123456789")
            admin = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))

            sys_reg = await register_system(session, actor=admin, name="HR API", description="HR")

            result = await configure_auth(
                session, system_id=sys_reg.id,
                auth_mode="token_exchange",
                token_endpoint_hint="https://idp.example.com/token",
            )
            assert result["auth_mode"] == "token_exchange"
            assert result["configured"] is True
            # Must never contain raw credentials
            result_str = str(result).lower()
            assert "bearer" not in result_str
            assert "password" not in result_str
            assert "secret" not in result_str
            assert "api_key" not in result_str

            await session.refresh(sys_reg)
            assert sys_reg.auth_config["auth_mode"] == "token_exchange"
            assert sys_reg.status == "auth_configured"

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
    asyncio.run(run())


def test_test_system_validates_offline():
    """Playground test validates the system configuration offline (no real network)."""
    import asyncio
    import subprocess

    from sqlalchemy import delete, func, select

    async def run():
        from e2eai.db import User, sessions
        from e2eai.seed import seed_demo
        from e2eai.system_registration import (
            SystemRegistration, register_system, upload_openapi_spec,
            set_allowed_operations, configure_auth, test_system,
        )

        async with sessions()() as session:
            await session.execute(delete(SystemRegistration))
            await session.commit()
            await seed_demo(session, password="TestPassword_123456789")
            admin = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))

            sys_reg = await register_system(session, actor=admin, name="HR API", description="HR")
            spec = {
                "openapi": "3.0.0",
                "info": {"title": "HR API", "version": "1.0.0"},
                "paths": {
                    "/employees": {
                        "get": {"operationId": "list_employees", "summary": "List", "responses": {"200": {"description": "OK"}}},
                    },
                },
            }
            await upload_openapi_spec(session, system_id=sys_reg.id, spec=spec)
            await set_allowed_operations(session, system_id=sys_reg.id, operation_ids=["list_employees"])
            await configure_auth(session, system_id=sys_reg.id, auth_mode="token_exchange")

            result = await test_system(session, system_id=sys_reg.id, actor=admin)
            assert result["status"] == "passed"
            assert result["checks"]["spec_uploaded"] is True
            assert result["checks"]["endpoints_selected"] is True
            assert result["checks"]["auth_configured"] is True
            assert result["checks"]["descriptor_valid"] is True

            await session.refresh(sys_reg)
            assert sys_reg.status == "tested"

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
    asyncio.run(run())


def test_grant_system_to_principals():
    """Admin grants system access to roles/divisions."""
    import asyncio
    import subprocess

    from sqlalchemy import delete, func, select

    async def run():
        from e2eai.db import User, sessions
        from e2eai.seed import seed_demo
        from e2eai.system_registration import (
            SystemRegistration, SystemGrant, register_system, grant_system,
        )

        async with sessions()() as session:
            await session.execute(delete(SystemGrant))
            await session.execute(delete(SystemRegistration))
            await session.commit()
            await seed_demo(session, password="TestPassword_123456789")
            admin = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))

            sys_reg = await register_system(session, actor=admin, name="HR API", description="HR")

            result = await grant_system(
                session, system_id=sys_reg.id,
                principals=["role:ai_engineer", "division:engineering"],
            )
            assert result["granted"] == ["role:ai_engineer", "division:engineering"]

            grants = (await session.execute(
                select(SystemGrant).where(SystemGrant.system_id == sys_reg.id)
            )).scalars().all()
            assert len(grants) == 2
            principals = {g.principal for g in grants}
            assert "role:ai_engineer" in principals
            assert "division:engineering" in principals

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
    asyncio.run(run())


def test_system_registration_output_never_contains_secrets():
    """All system registration outputs must be secret-safe."""
    import asyncio
    import subprocess

    from sqlalchemy import delete, func, select

    async def run():
        from e2eai.db import User, sessions
        from e2eai.seed import seed_demo
        from e2eai.system_registration import (
            SystemRegistration, register_system, configure_auth, safe_system_summary,
        )

        async with sessions()() as session:
            await session.execute(delete(SystemRegistration))
            await session.commit()
            await seed_demo(session, password="TestPassword_123456789")
            admin = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))

            sys_reg = await register_system(session, actor=admin, name="HR API", description="HR")
            await configure_auth(
                session, system_id=sys_reg.id,
                auth_mode="token_exchange",
                token_endpoint_hint="https://idp.example.com/oauth/token",
            )
            await session.refresh(sys_reg)

            summary = safe_system_summary(sys_reg)
            summary_str = str(summary).lower()
            assert "password" not in summary_str
            assert "secret" not in summary_str
            assert "bearer" not in summary_str
            assert "api_key" not in summary_str
            assert summary["name"] == "HR API"
            assert summary["auth_mode"] == "token_exchange"
            assert summary["status"] == "auth_configured"

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
    asyncio.run(run())


# ---------------------------------------------------------------------------
# Route wiring
# ---------------------------------------------------------------------------


def test_system_registration_routes_are_wired():
    """FR-X4 admin routes are registered in the FastAPI app."""
    from e2eai.main import app

    openapi = app.openapi()
    paths = openapi["paths"]
    assert "/api/v1/admin/systems" in paths, f"POST register not found. Paths: {sorted(paths.keys())}"
    assert "/api/v1/admin/systems/{system_id}/spec" in paths
    assert "/api/v1/admin/systems/{system_id}/endpoints" in paths
    assert "/api/v1/admin/systems/{system_id}/auth" in paths
    assert "/api/v1/admin/systems/{system_id}/test" in paths
    assert "/api/v1/admin/systems/{system_id}/grants" in paths
