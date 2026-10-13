"""NFR-10: admins are reminded once before a data-subject request deadline (and when it is overdue)."""

import asyncio
import subprocess
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select, update

from e2eai.core.errors import AppError


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


async def _setup(session):
    from e2eai.db import AuditEntry, Conversation, DataSubjectRequest, Document, Notification, User
    from e2eai.seed import ADMIN_EMAIL, bootstrap_admin, seed_demo

    await session.execute(update(Conversation).values(legal_hold=False))
    await session.execute(update(Document).values(legal_hold=False))
    await session.execute(delete(DataSubjectRequest))
    await session.execute(delete(Notification).where(Notification.kind == "dsr.deadline"))
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


def test_reminder_sent_once_to_admins_for_due_soon_and_overdue_requests_without_personal_data():
    async def run():
        from e2eai.data_subject import open_request, send_deadline_reminders
        from e2eai.db import Notification, User, sessions

        async with sessions()() as session:
            admin, andi, budi = await _setup(session)
            now = datetime.now(UTC)
            soon = await open_request(session, admin=admin, subject_id=andi.id, kind="export",
                                      received_at=now - timedelta(days=27))   # due in 3 days
            late = await open_request(session, admin=admin, subject_id=budi.id, kind="erase",
                                      received_at=now - timedelta(days=40))   # overdue
            await open_request(session, admin=admin, subject_id=budi.id, kind="export")  # far from deadline

            with pytest.raises(AppError) as exc:
                await send_deadline_reminders(session, admin=budi)
            assert exc.value.status == 403

            out = await send_deadline_reminders(session, admin=admin, within_days=5)
            assert sorted(out["reminded"]) == sorted([soon["id"], late["id"]])
            rows = (await session.scalars(select(Notification).where(Notification.kind == "dsr.deadline"))).all()
            from e2eai.db import Role, UserRole

            admin_ids = set((await session.scalars(
                select(User.id).join(UserRole, UserRole.user_id == User.id).join(Role, Role.id == UserRole.role_id)
                .where(Role.name == "admin", User.status == "active"))).all())
            assert admin.id in admin_ids and budi.id not in admin_ids
            assert {r.user_id for r in rows} == admin_ids  # every active admin, nobody else
            assert len(rows) == 2 * len(admin_ids)
            assert out["recipients"] == len(admin_ids)
            blob = repr([r.details for r in rows])
            assert "andi@demo.e2eai" not in blob and "Budi" not in blob
            assert {r.details["request_id"] for r in rows} == {soon["id"], late["id"]}
            assert {r.details["overdue"] for r in rows} == {False, True}

            again = await send_deadline_reminders(session, admin=admin, within_days=5)  # idempotent
            assert again["reminded"] == []
            assert len((await session.scalars(select(Notification).where(Notification.kind == "dsr.deadline"))).all()) == 2 * len(admin_ids)

    _migrate()
    asyncio.run(run())


def test_completed_requests_are_not_reminded_and_route_exists():
    async def run():
        from e2eai.data_subject import export_subject_data, open_request, send_deadline_reminders
        from e2eai.db import sessions
        from e2eai.main import create_app

        async with sessions()() as session:
            admin, andi, budi = await _setup(session)
            await open_request(session, admin=admin, subject_id=andi.id, kind="export",
                               received_at=datetime.now(UTC) - timedelta(days=29))
            await export_subject_data(session, admin=admin, subject_id=andi.id)
            assert (await send_deadline_reminders(session, admin=admin))["reminded"] == []
        assert "post" in create_app().openapi()["paths"]["/api/v1/privacy/requests/remind"]

    _migrate()
    asyncio.run(run())
