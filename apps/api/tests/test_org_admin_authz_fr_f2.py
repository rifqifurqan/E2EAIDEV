"""FR-F2 hardening: /api/v1/admin/org/* requires an authenticated admin; audit actor comes from the session."""

import asyncio
import subprocess
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from e2eai.auth import current_session
from e2eai.db import AuditEntry, Organization, User, UserRole, sessions as db_sessions
from e2eai.seed import seed_demo


def _migrate():
    result = subprocess.run(["uv", "run", "alembic", "upgrade", "head"], capture_output=True, text=True)
    if result.returncode != 0 and "ConnectionRefusedError" in result.stderr:
        pytest.skip("Postgres/Docker is unavailable; DB-backed org authz test skipped")
    result.check_returncode()


def _app(user_id: uuid.UUID | None) -> TestClient:
    from e2eai.core.errors import install
    from e2eai.org import router

    app = FastAPI()
    install(app)
    app.include_router(router)

    if user_id is not None:
        async def fake_session():
            return {"user_id": str(user_id), "auth_type": "session", "csrf": "x"}

        app.dependency_overrides[current_session] = fake_session
    return TestClient(app, raise_server_exceptions=False)


def _ids():
    async def run():
        async with db_sessions()() as s:
            await seed_demo(s, password="TestPassword_123456789")
            org = await s.scalar(select(Organization).where(Organization.name == "Demo"))
            andi = await s.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
            admin = await s.scalar(select(User).where(func.lower(User.email) == "admin@local"))
            if admin is None:  # demo seed has no admin: promote a fresh user
                from e2eai.db import Role
                role = await s.scalar(select(Role).where(Role.name == "admin"))
                admin = User(org_id=org.id, email=f"org-admin-{uuid.uuid4().hex[:8]}@demo.e2eai", display_name="Org Admin")
                s.add(admin)
                await s.flush()
                s.add(UserRole(user_id=admin.id, role_id=role.id))
                await s.commit()
            return org.id, andi.id, admin.id

    return asyncio.run(run())


def test_unauthenticated_caller_cannot_use_org_routes():
    _migrate()
    org_id, _, _ = _ids()
    c = _app(None)
    assert c.get("/api/v1/admin/org/snapshot", params={"org_id": str(org_id)}).status_code == 401
    assert c.post("/api/v1/admin/org/divisions", json={"org_id": str(org_id), "name": "X"}).status_code == 401
    assert (
        c.post(
            "/api/v1/admin/org/role-grants",
            json={"user_id": str(uuid.uuid4()), "role_name": "admin"},
        ).status_code
        == 401
    )


def test_non_admin_cannot_use_org_routes_or_self_grant_admin():
    _migrate()
    org_id, andi_id, _ = _ids()
    c = _app(andi_id)
    assert c.get("/api/v1/admin/org/snapshot", params={"org_id": str(org_id)}).status_code == 403
    r = c.post("/api/v1/admin/org/role-grants", json={"user_id": str(andi_id), "role_name": "admin"})
    assert r.status_code == 403


def test_admin_succeeds_and_audit_actor_is_the_session_user_not_the_body():
    _migrate()
    org_id, _, admin_id = _ids()
    c = _app(admin_id)
    assert c.get("/api/v1/admin/org/snapshot", params={"org_id": str(org_id)}).status_code == 200
    name = f"Authz Div {uuid.uuid4().hex[:8]}"
    r = c.post(
        "/api/v1/admin/org/divisions",
        json={"org_id": str(org_id), "name": name, "actor": "someone-else"},
    )
    assert r.status_code == 200, r.text
    division_id = r.json()["id"]

    async def audited():
        async with db_sessions()() as s:
            return await s.scalar(
                select(AuditEntry.actor).where(
                    AuditEntry.action == "org.division.create", AuditEntry.target == f"division:{division_id}"
                )
            )

    assert asyncio.run(audited()) == f"user:{admin_id}"
