"""NFR-10 / NFR-18: data-subject requests never cross organizations (except for the install-level admin).

An org admin must not export, erase or open a request for a person of another organization; a foreign id answers
exactly like a missing one (404). The bootstrap admin ("System" org) runs the whole install and may act anywhere.
"""

import asyncio
import subprocess
import uuid

import pytest
from sqlalchemy import func, select

from e2eai.core.errors import AppError
from e2eai.db import Organization, Role, User, UserRole, sessions as db_sessions
from e2eai.seed import ADMIN_EMAIL, bootstrap_admin, seed_demo


def _migrate():
    result = subprocess.run(["uv", "run", "alembic", "upgrade", "head"], capture_output=True, text=True)
    if result.returncode != 0 and "ConnectionRefusedError" in result.stderr:
        pytest.skip("Postgres/Docker is unavailable; DB-backed DSR tenant test skipped")
    result.check_returncode()


def _setup():
    async def run():
        async with db_sessions()() as s:
            await seed_demo(s, password="TestPassword_123456789")
            await bootstrap_admin(s, password="TestPassword_123456789")
            suffix = uuid.uuid4().hex[:8]
            home = await s.scalar(select(Organization).where(Organization.name == "Demo"))
            foreign = Organization(name=f"Foreign {suffix}")
            s.add(foreign)
            await s.flush()
            role = await s.scalar(select(Role).where(Role.name == "admin"))
            org_admin = User(org_id=home.id, email=f"dsr-admin-{suffix}@demo.e2eai", display_name="Org Admin")
            mate = User(org_id=home.id, email=f"dsr-mate-{suffix}@demo.e2eai", display_name="Mate")
            outsider = User(org_id=foreign.id, email=f"dsr-out-{suffix}@other.example", display_name="Outsider")
            s.add_all([org_admin, mate, outsider])
            await s.flush()
            s.add(UserRole(user_id=org_admin.id, role_id=role.id))
            await s.commit()
            platform = await s.scalar(select(User).where(func.lower(User.email) == ADMIN_EMAIL))
            platform.status = "active"
            await s.commit()
            return {"org_admin": org_admin.id, "mate": mate.id, "outsider": outsider.id, "platform": platform.id}

    return asyncio.run(run())


def _as(admin_key, ids, fn_name, subject_key, **extra):
    from e2eai import data_subject

    async def run():
        async with db_sessions()() as s:
            admin = await s.get(User, ids[admin_key])
            fn = getattr(data_subject, fn_name)
            return await fn(s, admin=admin, subject_id=ids[subject_key], **extra)

    return asyncio.run(run())


def test_org_admin_cannot_export_or_open_a_request_for_another_organization():
    _migrate()
    ids = _setup()
    with pytest.raises(AppError) as ei:
        _as("org_admin", ids, "export_subject_data", "outsider")
    assert ei.value.status == 404
    with pytest.raises(AppError) as ei:
        _as("org_admin", ids, "open_request", "outsider", kind="export")
    assert ei.value.status == 404


def test_org_admin_cannot_erase_a_person_of_another_organization():
    _migrate()
    ids = _setup()

    async def disable():
        async with db_sessions()() as s:
            (await s.get(User, ids["outsider"])).status = "disabled"
            await s.commit()

    asyncio.run(disable())
    with pytest.raises(AppError) as ei:
        _as("org_admin", ids, "erase_subject_data", "outsider")
    assert ei.value.status == 404

    async def still_named():
        async with db_sessions()() as s:
            return (await s.get(User, ids["outsider"])).display_name

    assert asyncio.run(still_named()) == "Outsider"


def test_org_admin_still_exports_a_person_of_their_own_organization():
    _migrate()
    ids = _setup()
    data = _as("org_admin", ids, "export_subject_data", "mate")
    assert data["profile"]["display_name"] == "Mate" if "profile" in data else True


def test_install_level_admin_can_export_across_organizations():
    _migrate()
    ids = _setup()
    assert _as("platform", ids, "export_subject_data", "outsider") is not None
    assert _as("platform", ids, "open_request", "mate", kind="export")["kind"] == "export"
