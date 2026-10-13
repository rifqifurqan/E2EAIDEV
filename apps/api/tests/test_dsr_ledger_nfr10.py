"""NFR-10: data-subject request ledger with deadlines (open -> completed by export/erase, overdue list)."""

import asyncio
import subprocess
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select

from e2eai.core.errors import AppError


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


async def _people(session):
    from e2eai.db import AuditEntry, DataSubjectRequest, User
    from e2eai.seed import ADMIN_EMAIL, bootstrap_admin, seed_demo

    from sqlalchemy import update

    from e2eai.db import Conversation, Document

    await session.execute(update(Conversation).values(legal_hold=False))  # shared DB: other tests leave holds
    await session.execute(update(Document).values(legal_hold=False))
    await session.execute(delete(DataSubjectRequest))
    await session.execute(delete(AuditEntry).where(AuditEntry.action.like("dsr.%")))
    await session.commit()
    erased = await session.scalar(select(User).where(User.email.like("erased-%@erased.invalid")).limit(1))
    if erased is not None:
        erased.email, erased.display_name = "andi@demo.e2eai", "Andi"
        await session.commit()
    await seed_demo(session, password="TestPassword_123456789")
    await bootstrap_admin(session, password="TestPassword_123456789")
    q = lambda e: select(User).where(func.lower(User.email) == e)  # noqa: E731
    admin = await session.scalar(q(ADMIN_EMAIL))
    andi = await session.scalar(q("andi@demo.e2eai"))
    budi = await session.scalar(q("budi@demo.e2eai"))
    admin.status = andi.status = budi.status = "active"
    await session.commit()
    return admin, andi, budi


def test_open_request_sets_30_day_deadline_and_is_admin_only():
    async def run():
        from e2eai.data_subject import open_request
        from e2eai.db import sessions

        async with sessions()() as session:
            admin, andi, budi = await _people(session)
            now = datetime(2026, 10, 1, tzinfo=UTC)
            req = await open_request(session, admin=admin, subject_id=andi.id, kind="export", received_at=now)
            assert req["status"] == "open" and req["kind"] == "export"
            assert datetime.fromisoformat(req["due_at"]) == now + timedelta(days=30)
            with pytest.raises(AppError) as exc:
                await open_request(session, admin=budi, subject_id=andi.id, kind="export")
            assert exc.value.status == 403
            with pytest.raises(AppError) as exc:
                await open_request(session, admin=admin, subject_id=andi.id, kind="delete-everything")
            assert exc.value.status == 422

    _migrate()
    asyncio.run(run())


def test_export_closes_the_open_request_and_overdue_listing_flags_late_ones():
    async def run():
        from e2eai.data_subject import export_subject_data, list_requests_page, open_request
        from e2eai.db import sessions

        async with sessions()() as session:
            admin, andi, budi = await _people(session)
            old = datetime.now(UTC) - timedelta(days=45)
            late = await open_request(session, admin=admin, subject_id=budi.id, kind="export", received_at=old)
            fresh = await open_request(session, admin=admin, subject_id=andi.id, kind="export")

            items, _ = await list_requests_page(session, admin=admin, overdue_only=True)
            assert [i["id"] for i in items] == [late["id"]] and items[0]["overdue"] is True

            await export_subject_data(session, admin=admin, subject_id=andi.id)
            items, _ = await list_requests_page(session, admin=admin, status="completed")
            assert [i["id"] for i in items] == [fresh["id"]]
            assert items[0]["completed_at"] is not None and items[0]["overdue"] is False

            # export for a subject with no open request still works and creates no phantom ledger row
            items, _ = await list_requests_page(session, admin=admin)
            assert len(items) == 2

    _migrate()
    asyncio.run(run())


def test_erase_closes_request_pages_walk_and_ledger_holds_no_personal_data():
    async def run():
        from e2eai.data_subject import erase_subject_data, list_requests_page, open_request
        from e2eai.db import User, sessions

        async with sessions()() as session:
            admin, andi, budi = await _people(session)
            andi.status = "disabled"
            await session.commit()
            for _ in range(3):
                await open_request(session, admin=admin, subject_id=budi.id, kind="export")
            er = await open_request(session, admin=admin, subject_id=andi.id, kind="erase")
            await erase_subject_data(session, admin=admin, subject_id=andi.id)

            seen, cursor = [], None
            for _ in range(5):
                items, cursor = await list_requests_page(session, admin=admin, limit=2, cursor=cursor)
                seen += [i["id"] for i in items]
                if cursor is None:
                    break
            assert len(seen) == len(set(seen)) == 4
            done, _ = await list_requests_page(session, admin=admin, status="completed")
            assert [i["id"] for i in done] == [er["id"]]
            blob = repr(done) + repr(items)
            assert "andi@demo.e2eai" not in blob and "Budi" not in blob  # ids only

            with pytest.raises(AppError) as exc:
                await list_requests_page(session, admin=budi)
            assert exc.value.status == 403

            from e2eai.main import create_app
            paths = create_app().openapi()["paths"]
            assert {"get", "post"} <= set(paths["/api/v1/privacy/requests"])

            # leave the shared DB as found: erase pseudonymises Andi, other tests expect the demo user back
            gone = await session.scalar(select(User).where(User.email.like("erased-%@erased.invalid")).limit(1))
            if gone is not None:
                gone.email, gone.display_name, gone.status = "andi@demo.e2eai", "Andi", "active"
                await session.commit()

    _migrate()
    asyncio.run(run())
