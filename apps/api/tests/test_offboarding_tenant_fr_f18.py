"""FR-F18 / NFR-18: offboarding never crosses organizations.

An admin of org A must not be able to deactivate a user of org B, nor hand documents to a user of org B.
Foreign ids answer exactly like missing ids (404 / 400) so they cannot be probed.
"""

import asyncio
import subprocess
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy import update as sql_update

from e2eai.core.errors import AppError
from e2eai.db import Organization, User, sessions as db_sessions
from e2eai.seed import seed_demo


class _Authz:
    async def write(self, writes=(), deletes=()):
        return None


class _Redis:
    async def scan(self, cursor=0, match=None, count=100):
        return (0, [])

    async def get(self, key):
        return None

    async def delete(self, *keys):
        return 0


def _migrate():
    result = subprocess.run(["uv", "run", "alembic", "upgrade", "head"], capture_output=True, text=True)
    if result.returncode != 0 and "ConnectionRefusedError" in result.stderr:
        pytest.skip("Postgres/Docker is unavailable; DB-backed offboarding tenant test skipped")
    result.check_returncode()


def _setup():
    async def run():
        async with db_sessions()() as s:
            await seed_demo(s, password="TestPassword_123456789")
            suffix = uuid.uuid4().hex[:8]
            home = await s.scalar(select(Organization).where(Organization.name == "Demo"))
            foreign = Organization(name=f"Foreign {suffix}")
            s.add(foreign)
            await s.flush()
            admin = User(org_id=home.id, email=f"off-admin-{suffix}@demo.e2eai", display_name="Admin")
            mate = User(org_id=home.id, email=f"off-mate-{suffix}@demo.e2eai", display_name="Mate")
            target = User(org_id=home.id, email=f"off-target-{suffix}@demo.e2eai", display_name="Target")
            outsider = User(org_id=foreign.id, email=f"off-out-{suffix}@other.example", display_name="Outsider")
            outsider2 = User(org_id=foreign.id, email=f"off-out2-{suffix}@other.example", display_name="Outsider2")
            s.add_all([admin, mate, target, outsider, outsider2])
            await s.commit()
            from e2eai.seed import ADMIN_EMAIL, bootstrap_admin

            await bootstrap_admin(s, password="TestPassword_123456789")
            platform = await s.scalar(select(User).where(func.lower(User.email) == ADMIN_EMAIL))
            ids = {k: v.id for k, v in dict(admin=admin, mate=mate, target=target, outsider=outsider, outsider2=outsider2).items()}
            ids["platform"] = platform.id
            return ids

    return asyncio.run(run())


async def _call(ids, *, target, transfer_to, admin="admin"):
    from e2eai.offboarding import deactivate_user

    async with db_sessions()() as s:
        admin = await s.get(User, ids[admin])
        return await deactivate_user(s, _Redis(), _Authz(), admin=admin, target_user_id=ids[target], transfer_to_id=ids[transfer_to])


async def _status(user_id):
    async with db_sessions()() as s:
        return (await s.get(User, user_id)).status


def test_admin_cannot_deactivate_a_user_of_another_organization():
    _migrate()
    ids = _setup()
    with pytest.raises(AppError) as ei:
        asyncio.run(_call(ids, target="outsider", transfer_to="mate"))
    assert ei.value.status == 404
    assert asyncio.run(_status(ids["outsider"])) == "active"


def test_admin_cannot_transfer_assets_to_a_user_of_another_organization():
    _migrate()
    ids = _setup()
    with pytest.raises(AppError) as ei:
        asyncio.run(_call(ids, target="target", transfer_to="outsider"))
    assert ei.value.status == 400
    assert asyncio.run(_status(ids["target"])) == "active"


def test_same_organization_offboarding_still_works():
    _migrate()
    ids = _setup()
    result = asyncio.run(_call(ids, target="target", transfer_to="mate"))
    assert result["status"] == "disabled"
    assert asyncio.run(_status(ids["target"])) == "disabled"


def test_install_level_admin_can_offboard_within_the_target_organization():
    _migrate()
    ids = _setup()
    result = asyncio.run(_call(ids, target="target", transfer_to="mate", admin="platform"))
    assert result["status"] == "disabled"


def test_install_level_admin_still_cannot_move_assets_into_a_different_organization():
    _migrate()
    ids = _setup()
    with pytest.raises(AppError) as ei:
        asyncio.run(_call(ids, target="target", transfer_to="outsider", admin="platform"))
    assert ei.value.status == 400
    assert asyncio.run(_status(ids["target"])) == "active"


def teardown_module(module):
    async def cleanup():
        async with db_sessions()() as s:
            await s.execute(sql_update(User).where(User.status == "disabled").values(status="active"))
            await s.commit()

    asyncio.run(cleanup())
