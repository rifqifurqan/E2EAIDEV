"""FR-S8 org-change-driven access updates from SCIM.

Deterministic/offline: SCIM-style user/group payloads are applied to the org model. Moving divisions
loses the old division's access and gains the new one (principals come from the org tables, so the
change takes effect immediately; OpenFGA membership tuples are corrected in the same sync).
Deprovisioning (active=false) reuses the FR-F18 offboarding flow. Unknown departments fail closed.
"""

import asyncio
import subprocess

import pytest
from sqlalchemy import delete, select

from e2eai.core.errors import AppError
from e2eai.db import AuditEntry, Division, Organization, Team, TeamMember, User, sessions


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


class RecordingAuthz:
    def __init__(self):
        self.writes, self.deletes = [], []

    async def write(self, writes=(), deletes=()):
        self.writes += list(writes)
        self.deletes += list(deletes)


class FakeRedis:
    async def scan(self, cursor, match=None, count=None):
        return 0, []

    async def get(self, key):
        return None

    async def delete(self, *keys):
        return 0


EMAILS = ["scim.one@scim.test", "scim.two@scim.test"]


async def _setup(session):
    from e2eai.authz import principals  # noqa: F401  (import check)
    from e2eai.seed import ADMIN_EMAIL, bootstrap_admin, seed_demo

    await seed_demo(session, password="TestPassword_123456789")
    await bootstrap_admin(session, password="TestPassword_123456789")
    await _cleanup(session)
    admin = await session.scalar(select(User).where(User.email == ADMIN_EMAIL))
    # SCIM maps departments only inside the acting admin's own organization (NFR-18, org confinement),
    # so the divisions under test must live in the admin's org, not in whichever org sorts first.
    org = await session.get(Organization, admin.org_id)
    sales = Division(org_id=org.id, name="SCIM Sales")
    hr = Division(org_id=org.id, name="SCIM HR")
    session.add_all([sales, hr])
    await session.flush()
    team = Team(division_id=sales.id, name="SCIM Field Team")
    session.add(team)
    await session.commit()
    return admin, org, sales, hr, team


async def _cleanup(session):
    await session.execute(delete(AuditEntry).where(AuditEntry.action.like("scim.%")))
    ids = (await session.scalars(select(User.id).where(User.email.in_(EMAILS)))).all()
    if ids:
        await session.execute(delete(TeamMember).where(TeamMember.user_id.in_(ids)))
        await session.execute(delete(User).where(User.id.in_(ids)))
    await session.execute(delete(Team).where(Team.name == "SCIM Field Team"))
    await session.execute(delete(Division).where(Division.name.in_(["SCIM Sales", "SCIM HR"])))
    await session.commit()


def _user(email, dept=None, active=True, name="SCIM User"):
    payload = {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "userName": email, "displayName": name, "active": active,
        "emails": [{"value": email, "primary": True}],
    }
    if dept is not None:
        payload["urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"] = {"department": dept}
    return payload


def test_provision_then_move_division_swaps_access_and_openfga_tuples():
    async def run():
        from e2eai.authz import principals
        from e2eai.scim_sync import sync_scim

        async with sessions()() as session:
            admin, org, sales, hr, team = await _setup(session)
            try:
                authz = RecordingAuthz()
                r1 = await sync_scim(session, FakeRedis(), authz, actor=admin, users=[_user(EMAILS[0], "SCIM Sales")])
                assert r1["users"][0]["action"] == "created" and r1["created"] == 1
                u = await session.scalar(select(User).where(User.email == EMAILS[0]))
                assert u.division_id == sales.id and f"division:{sales.id}" in await principals(session, u)

                again = await sync_scim(session, FakeRedis(), RecordingAuthz(), actor=admin, users=[_user(EMAILS[0], "SCIM Sales")])
                assert again["unchanged"] == 1 and again["users"][0]["action"] == "unchanged"

                authz2 = RecordingAuthz()
                moved = await sync_scim(session, FakeRedis(), authz2, actor=admin, users=[_user(EMAILS[0], "scim hr")])
                assert moved["users"][0]["action"] == "updated" and moved["users"][0]["division_changed"] is True
                await session.refresh(u)
                p = await principals(session, u)
                assert f"division:{hr.id}" in p and f"division:{sales.id}" not in p  # lost old, gained new
                assert any(d["object"] == f"division:{sales.id}" for d in authz2.deletes)
                assert any(w["object"] == f"division:{hr.id}" for w in authz2.writes)
            finally:
                await _cleanup(session)

    _migrate()
    asyncio.run(run())


def test_unknown_department_fails_closed_and_is_reported():
    async def run():
        from e2eai.authz import principals
        from e2eai.scim_sync import sync_scim

        async with sessions()() as session:
            admin, org, sales, hr, team = await _setup(session)
            try:
                await sync_scim(session, FakeRedis(), RecordingAuthz(), actor=admin, users=[_user(EMAILS[0], "SCIM Sales")])
                res = await sync_scim(session, FakeRedis(), RecordingAuthz(), actor=admin, users=[_user(EMAILS[0], "Mystery Dept")])
                assert res["users"][0]["warnings"] == ["unmapped_department"]
                u = await session.scalar(select(User).where(User.email == EMAILS[0]))
                assert u.division_id is None  # old division access dropped, nothing new granted
                assert not [x for x in await principals(session, u) if x.startswith("division:")]
            finally:
                await _cleanup(session)

    _migrate()
    asyncio.run(run())


def test_group_sync_adds_and_removes_team_members_by_email():
    async def run():
        from e2eai.authz import principals
        from e2eai.scim_sync import sync_scim

        async with sessions()() as session:
            admin, org, sales, hr, team = await _setup(session)
            try:
                users = [_user(EMAILS[0], "SCIM Sales"), _user(EMAILS[1], "SCIM Sales", name="Two")]
                grp = lambda members: {"displayName": "SCIM Field Team", "members": [{"value": m} for m in members]}  # noqa: E731
                await sync_scim(session, FakeRedis(), RecordingAuthz(), actor=admin, users=users, groups=[grp(EMAILS)])
                one = await session.scalar(select(User).where(User.email == EMAILS[0]))
                assert f"team:{team.id}" in await principals(session, one)

                authz = RecordingAuthz()
                res = await sync_scim(session, FakeRedis(), authz, actor=admin, users=users, groups=[grp([EMAILS[1]])])
                assert res["groups"][0] == {"group": "SCIM Field Team", "added": 0, "removed": 1, "unknown_members": 0}
                assert f"team:{team.id}" not in await principals(session, one)
                assert any(d["object"] == f"team:{team.id}" for d in authz.deletes)

                unknown = await sync_scim(session, FakeRedis(), RecordingAuthz(), actor=admin, groups=[
                    {"displayName": "SCIM Field Team", "members": [{"value": "ghost@nowhere.test"}, {"value": EMAILS[1]}]},
                ])
                assert unknown["groups"][0]["unknown_members"] == 1
                missing = await sync_scim(session, FakeRedis(), RecordingAuthz(), actor=admin, groups=[{"displayName": "No Such Team", "members": []}])
                assert missing["groups"][0]["warnings"] == ["unmapped_group"]
            finally:
                await _cleanup(session)

    _migrate()
    asyncio.run(run())


def test_deprovision_disables_user_and_non_admin_is_rejected():
    async def run():
        from e2eai.scim_sync import sync_scim

        async with sessions()() as session:
            admin, org, sales, hr, team = await _setup(session)
            try:
                await sync_scim(session, FakeRedis(), RecordingAuthz(), actor=admin, users=[_user(EMAILS[0], "SCIM Sales")])
                res = await sync_scim(session, FakeRedis(), RecordingAuthz(), actor=admin, users=[_user(EMAILS[0], "SCIM Sales", active=False)])
                assert res["users"][0]["action"] == "deactivated" and res["deactivated"] == 1
                u = await session.scalar(select(User).where(User.email == EMAILS[0]))
                assert u.status == "disabled"
                # a never-seen inactive user is not created
                skipped = await sync_scim(session, FakeRedis(), RecordingAuthz(), actor=admin, users=[_user(EMAILS[1], active=False)])
                assert skipped["users"][0]["action"] == "skipped_inactive"
                assert await session.scalar(select(User).where(User.email == EMAILS[1])) is None

                andi = await session.scalar(select(User).where(User.email == "andi@demo.e2eai"))
                with pytest.raises(AppError) as exc:
                    await sync_scim(session, FakeRedis(), RecordingAuthz(), actor=andi, users=[_user(EMAILS[1])])
                assert exc.value.status == 403

                audits = (await session.scalars(select(AuditEntry).where(AuditEntry.action.like("scim.%")))).all()
                assert audits and all("@" not in str(a.details) for a in audits)
            finally:
                await _cleanup(session)

    _migrate()
    asyncio.run(run())


def test_route_is_wired():
    from e2eai.main import app

    assert "post" in app.openapi()["paths"]["/api/v1/scim/sync"]
