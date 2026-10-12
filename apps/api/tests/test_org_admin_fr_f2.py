"""FR-F2: admin/service CRUD for org hierarchy, memberships, role grants, and project ownership."""

import asyncio
import subprocess
import uuid

import pytest
from sqlalchemy import func, select

from e2eai.db import AuditEntry, Organization, TeamMember, UserRole, sessions as db_sessions
from e2eai.seed import seed_demo


def _migrate():
    result = subprocess.run(["uv", "run", "alembic", "upgrade", "head"], capture_output=True, text=True)
    if result.returncode != 0 and "ConnectionRefusedError" in result.stderr:
        pytest.skip("Postgres/Docker is unavailable in this cron environment; DB-backed FR-F2 service smoke skipped")
    result.check_returncode()


def test_admin_org_service_creates_hierarchy_memberships_roles_and_project_ownership():
    """Admin CRUD service creates the FR-F2 org slice and audits each access-relevant change."""
    from e2eai.org import (
        add_team_member,
        create_division,
        create_project,
        create_team,
        create_user,
        grant_role,
        org_snapshot,
        update_project_owner,
    )

    async def run():
        async with db_sessions()() as session:
            await seed_demo(session, password="TestPassword_123456789")
            org = await session.scalar(select(Organization).where(Organization.name == "Demo"))
            assert org is not None
            suffix = uuid.uuid4().hex[:8]

            division = await create_division(session, org_id=org.id, name=f"Ops {suffix}", actor="admin:test")
            team = await create_team(session, division_id=division.id, name=f"Ops AI {suffix}", actor="admin:test")
            user = await create_user(
                session,
                org_id=org.id,
                email=f"ops-{suffix}@demo.e2eai",
                display_name="Ops User",
                division_id=division.id,
                actor="admin:test",
            )
            membership = await add_team_member(session, team_id=team.id, user_id=user.id, actor="admin:test")
            project = await create_project(
                session,
                org_id=org.id,
                name=f"Ops Project {suffix}",
                owner_team_id=team.id,
                actor="admin:test",
            )
            await update_project_owner(
                session,
                project_id=project.id,
                owner_team_id=None,
                owner_division_id=division.id,
                actor="admin:test",
            )
            grant = await grant_role(
                session,
                user_id=user.id,
                role_name="ai_engineer",
                project_id=project.id,
                actor="admin:test",
            )
            await session.commit()

            assert membership.team_id == team.id and membership.user_id == user.id
            assert grant.user_id == user.id and grant.project_id == project.id
            assert await session.scalar(select(TeamMember).where(TeamMember.team_id == team.id, TeamMember.user_id == user.id))
            assert await session.scalar(select(UserRole).where(UserRole.user_id == user.id, UserRole.project_id == project.id))

            snapshot = await org_snapshot(session, org_id=org.id, project_id=project.id)
            assert {d["id"] for d in snapshot["divisions"]} >= {str(division.id)}
            assert {t["id"] for t in snapshot["teams"]} >= {str(team.id)}
            assert {u["id"] for u in snapshot["users"]} >= {str(user.id)}
            assert {p["id"] for p in snapshot["projects"]} >= {str(project.id)}
            assert snapshot["role_grants"][str(user.id)] == ["ai_engineer"]
            assert snapshot["projects_by_id"][str(project.id)]["owner_division_id"] == str(division.id)
            assert snapshot["projects_by_id"][str(project.id)]["owner_team_id"] is None

            audited = await session.scalar(select(func.count()).select_from(AuditEntry).where(AuditEntry.actor == "admin:test"))
            assert audited >= 7

    _migrate()
    asyncio.run(run())


def test_admin_org_router_is_registered_with_safe_fr_f2_routes():
    """The API exposes explicit admin org routes; no route should rely on unscoped generic DB access."""
    from e2eai.main import create_app

    schema_paths = set(create_app().openapi()["paths"])
    assert "/api/v1/admin/org/divisions" in schema_paths
    assert "/api/v1/admin/org/teams" in schema_paths
    assert "/api/v1/admin/org/users" in schema_paths
    assert "/api/v1/admin/org/team-memberships" in schema_paths
    assert "/api/v1/admin/org/role-grants" in schema_paths
    assert "/api/v1/admin/org/projects" in schema_paths
