"""NFR-20: cursor pagination on the notifications and incidents list helpers."""

import asyncio
import subprocess

from sqlalchemy import delete, func, select

from e2eai.db import AIIncident, AuditEntry, Notification, User, sessions
from e2eai.seed import ADMIN_EMAIL, bootstrap_admin, seed_demo


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


def test_notification_pages_walk_every_row_once_and_stay_owner_scoped():
    from e2eai.notifications import list_notifications_page, notify_release_approved
    import uuid

    async def run():
        async with sessions()() as s:
            await s.execute(delete(Notification))
            await s.commit()
            await seed_demo(s, password="TestPassword_123456789")
            andi = await s.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
            budi = await s.scalar(select(User).where(func.lower(User.email) == "budi@demo.e2eai"))
            for i in range(5):
                await notify_release_approved(s, actor=budi, recipient=andi, bot_id=uuid.uuid4(),
                                              bot_name=f"bot{i}", version=i, environment="prod", approval_id=uuid.uuid4())
            await notify_release_approved(s, actor=andi, recipient=budi, bot_id=uuid.uuid4(),
                                          bot_name="budi-only", version=1, environment="prod", approval_id=uuid.uuid4())
            seen, cursor = [], None
            while True:
                items, cursor = await list_notifications_page(s, user=andi, limit=2, cursor=cursor)
                assert len(items) <= 2
                seen += [n.id for n in items]
                if cursor is None:
                    break
            assert len(seen) == 5 and len(set(seen)) == 5
            first, nxt = await list_notifications_page(s, user=andi, limit=2)
            assert nxt is not None
            other, _ = await list_notifications_page(s, user=budi, limit=50, cursor=nxt)
            assert all(n.user_id == budi.id for n in other)  # a cursor never widens ownership
            unread, _ = await list_notifications_page(s, user=andi, limit=50, unread_only=True)
            assert len(unread) == 5

    _migrate()
    asyncio.run(run())


def test_incident_pages_walk_every_row_once_and_filter_by_status():
    from e2eai.incidents import list_incidents_page, report_incident

    async def run():
        async with sessions()() as s:
            await s.execute(delete(AuditEntry).where(AuditEntry.action.like("incident.%")))
            await s.execute(delete(AIIncident))
            await s.commit()
            await seed_demo(s, password="TestPassword_123456789")
            await bootstrap_admin(s, password="TestPassword_123456789")
            admin = await s.scalar(select(User).where(func.lower(User.email) == ADMIN_EMAIL))
            for i in range(5):
                await report_incident(s, actor=admin, title=f"inc{i}", severity="sev3")
            seen, cursor = [], None
            while True:
                items, cursor = await list_incidents_page(s, limit=2, cursor=cursor)
                assert len(items) <= 2
                seen += [i["id"] for i in items]
                if cursor is None:
                    break
            assert len(seen) == 5 and len(set(seen)) == 5
            none, nxt = await list_incidents_page(s, limit=2, status="closed")
            assert none == [] and nxt is None

    _migrate()
    asyncio.run(run())
