"""NFR-20: every record has created/updated by and at; the actor is filled in automatically."""

import asyncio
import subprocess

from sqlalchemy import delete, func, select

AUDIT_COLS = ("created_at", "updated_at", "created_by", "updated_by")


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


def test_every_entity_table_has_created_updated_by_and_at_or_a_documented_exemption():
    from e2eai.db import AUDIT_EXEMPT_TABLES, Base

    assert all(reason.strip() for reason in AUDIT_EXEMPT_TABLES.values()), "each exemption needs a reason"
    missing = {}
    for table in Base.metadata.tables.values():
        if table.name in AUDIT_EXEMPT_TABLES:
            continue
        gap = [c for c in AUDIT_COLS if c not in table.columns]
        if gap:
            missing[table.name] = gap
    assert missing == {}
    assert set(AUDIT_EXEMPT_TABLES) <= set(Base.metadata.tables), "exemption names a table that does not exist"


def test_actor_is_filled_on_insert_and_update_but_explicit_values_and_noop_changes_are_kept():
    async def run():
        from e2eai.core.audit_actor import actor_scope
        from e2eai.db import Prompt, User, sessions
        from e2eai.seed import ADMIN_EMAIL, bootstrap_admin, seed_demo

        async with sessions()() as session:
            await seed_demo(session, password="TestPassword_123456789")
            await bootstrap_admin(session, password="TestPassword_123456789")
            admin = await session.scalar(select(User).where(func.lower(User.email) == ADMIN_EMAIL))
            await session.execute(delete(Prompt).where(Prompt.name.like("nfr20-%")))
            await session.commit()

            with actor_scope(f"user:{admin.id}"):
                auto = Prompt(owner_id=admin.id, name="nfr20-auto")
                explicit = Prompt(owner_id=admin.id, name="nfr20-explicit", created_by="oidc:abc")
                session.add_all([auto, explicit])
                await session.commit()
            assert auto.created_by == f"user:{admin.id}"
            assert explicit.created_by == "oidc:abc"  # never overwritten
            assert auto.updated_by is None  # inserts only set created_by

            with actor_scope("user:someone-else"):
                auto.name = "nfr20-auto"  # same value: no net change, must not stamp updated_by
                await session.commit()
            assert auto.updated_by is None

            with actor_scope("user:someone-else"):
                auto.name = "nfr20-auto-renamed"
                await session.commit()
            assert auto.updated_by == "user:someone-else"
            assert auto.created_by == f"user:{admin.id}"  # creator preserved

            await session.execute(delete(Prompt).where(Prompt.name.like("nfr20-%")))
            await session.commit()

    _migrate()
    asyncio.run(run())


def test_without_an_actor_scope_rows_stay_system_written_and_scope_resets():
    from e2eai.core.audit_actor import actor_scope, current_actor

    assert current_actor() is None
    with actor_scope("user:x"):
        assert current_actor() == "user:x"
        with actor_scope("user:y"):
            assert current_actor() == "user:y"
        assert current_actor() == "user:x"
    assert current_actor() is None
