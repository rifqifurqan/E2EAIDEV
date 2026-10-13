"""NFR-10: self-service data-subject requests (own export, own request filing) without widening access."""

import asyncio
import subprocess

import pytest
from sqlalchemy import delete, func, select, update

from e2eai.core.errors import AppError


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


async def _setup(session):
    from e2eai.chat import create_conversation
    from e2eai.db import AuditEntry, Conversation, DataSubjectRequest, Document, Message, User
    from e2eai.seed import ADMIN_EMAIL, bootstrap_admin, seed_demo

    await session.execute(update(Conversation).values(legal_hold=False))
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
    for user, text in ((andi, "andi-private-text"), (budi, "budi-private-text")):
        conv = await create_conversation(session, user=user, title=f"{text} chat")
        session.add(Message(conversation_id=conv.id, role="user", content=text))
    await session.commit()
    return admin, andi, budi


def test_user_exports_only_own_data_and_it_closes_own_open_export_request():
    async def run():
        from e2eai.data_subject import export_own_data, list_own_requests_page, open_own_request
        from e2eai.db import AuditEntry, sessions

        async with sessions()() as session:
            admin, andi, budi = await _setup(session)
            req = await open_own_request(session, user=andi, kind="export")
            assert req["status"] == "open" and req["subject_id"] == str(andi.id)

            data = await export_own_data(session, user=andi)
            blob = repr(data)
            assert "andi-private-text" in blob and "budi-private-text" not in blob
            assert data["profile"]["id"] == str(andi.id)
            assert "password" not in blob.lower()

            items, _ = await list_own_requests_page(session, user=andi)
            assert [i["id"] for i in items] == [req["id"]] and items[0]["status"] == "completed"
            other, _ = await list_own_requests_page(session, user=budi)
            assert other == []  # nobody sees another person's ledger rows

            entry = await session.scalar(select(AuditEntry).where(AuditEntry.action == "dsr.self_export")
                                         .order_by(AuditEntry.seq.desc()).limit(1))
            assert entry.actor == f"user:{andi.id}" and "andi-private-text" not in repr(entry.details)

    _migrate()
    asyncio.run(run())


def test_self_erase_is_only_a_request_nothing_is_deleted_and_inactive_users_are_refused():
    async def run():
        from e2eai.data_subject import list_requests_page, open_own_request
        from e2eai.db import Conversation, sessions

        async with sessions()() as session:
            admin, andi, budi = await _setup(session)
            before = await session.scalar(select(func.count()).select_from(Conversation).where(
                Conversation.user_id == andi.id))
            req = await open_own_request(session, user=andi, kind="erase")
            assert req["kind"] == "erase" and req["status"] == "open"
            after = await session.scalar(select(func.count()).select_from(Conversation).where(
                Conversation.user_id == andi.id))
            assert before == after and after > 0  # an admin must still run the erase after offboarding

            queue, _ = await list_requests_page(session, admin=admin, status="open")
            assert req["id"] in [i["id"] for i in queue]  # visible to the admin queue

            with pytest.raises(AppError) as exc:
                await open_own_request(session, user=andi, kind="rectify")
            assert exc.value.status == 422
            budi.status = "disabled"
            await session.commit()
            with pytest.raises(AppError) as exc:
                await open_own_request(session, user=budi, kind="export")
            assert exc.value.status == 403
            budi.status = "active"
            await session.commit()

    _migrate()
    asyncio.run(run())


def test_self_service_routes_exist():
    from e2eai.main import create_app

    paths = create_app().openapi()["paths"]
    assert "get" in paths["/api/v1/privacy/me/export"]
    assert {"get", "post"} <= set(paths["/api/v1/privacy/me/requests"])
