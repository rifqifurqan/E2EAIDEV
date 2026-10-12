"""NFR-10 data-subject requests: export a person's data, erase it (pseudonymise), respecting legal hold.

Deterministic/offline. Export carries the person's own conversations/messages/memories/notifications and
profile only (no credentials, hashes, or other people's data). Erasure requires an offboarded (disabled) user,
refuses when any of their chats or documents is under legal hold, and keeps the append-only audit log intact.
"""

import asyncio
import subprocess

import pytest
from sqlalchemy import delete, func, select


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


async def _setup(session):
    from e2eai.chat import create_conversation
    from e2eai.db import (
        Conversation, Message, MessageCitation, MessageFeedback, Notification, User, UserMemory, UserMemorySetting,
    )
    from e2eai.seed import ADMIN_EMAIL, bootstrap_admin, seed_demo

    for m in (MessageFeedback, MessageCitation, Message, Conversation, Notification, UserMemory, UserMemorySetting):
        await session.execute(delete(m))
    await session.commit()
    # An earlier erase test pseudonymises Andi in the shared DB; restore him so every test starts the same.
    erased = await session.scalar(select(User).where(User.email.like("erased-%@erased.invalid")).limit(1))
    if erased is not None:
        erased.email, erased.display_name = "andi@demo.e2eai", "Andi"
        await session.commit()
    await seed_demo(session, password="TestPassword_123456789")
    await bootstrap_admin(session, password="TestPassword_123456789")
    q = lambda e: select(User).where(func.lower(User.email) == e)  # noqa: E731
    owner = await session.scalar(q(ADMIN_EMAIL))  # the only admin; Andi and Budi are ordinary users
    andi = await session.scalar(q("andi@demo.e2eai"))
    budi = await session.scalar(q("budi@demo.e2eai"))
    owner.status = andi.status = budi.status = "active"
    await session.commit()
    conv = await create_conversation(session, user=andi, title="Gaji saya")
    session.add(Message(conversation_id=conv.id, role="user", content="Berapa cuti saya?"))
    session.add(Message(conversation_id=conv.id, role="assistant", content="12 hari."))
    session.add(Notification(user_id=andi.id, kind="review.assigned", details={"doc": "x"}))
    session.add(UserMemory(user_id=andi.id, text="suka jawaban singkat"))
    other = await create_conversation(session, user=budi, title="Budi rahasia")
    session.add(Message(conversation_id=other.id, role="user", content="budi-only-text"))
    await session.commit()
    return owner, andi, budi, conv


def test_export_contains_only_the_subjects_data_and_no_credentials():
    async def run():
        from e2eai.data_subject import export_subject_data
        from e2eai.db import sessions

        async with sessions()() as s:
            owner, andi, budi, _ = await _setup(s)
            data = await export_subject_data(s, admin=owner, subject_id=andi.id)
            text = repr(data)
            assert data["profile"]["email"] == "andi@demo.e2eai"
            assert [c["title"] for c in data["conversations"]] == ["Gaji saya"]
            assert {m["content"] for m in data["conversations"][0]["messages"]} == {"Berapa cuti saya?", "12 hari."}
            assert data["memories"][0]["text"] == "suka jawaban singkat"
            assert data["notifications"][0]["kind"] == "review.assigned"
            assert "budi-only-text" not in text and "Budi rahasia" not in text
            assert "password" not in text.lower() and "hash" not in text.lower()

    _migrate()
    asyncio.run(run())


def test_export_and_erase_are_admin_only_and_audited_without_content():
    async def run():
        from e2eai.core.errors import AppError
        from e2eai.data_subject import export_subject_data
        from e2eai.db import AuditEntry, sessions

        async with sessions()() as s:
            owner, andi, budi, _ = await _setup(s)
            with pytest.raises(AppError) as e:
                await export_subject_data(s, admin=budi, subject_id=andi.id)
            assert e.value.status == 403
            await export_subject_data(s, admin=owner, subject_id=andi.id)
            row = (await s.execute(select(AuditEntry).where(AuditEntry.action == "dsr.export")
                                   .order_by(AuditEntry.seq.desc()).limit(1))).scalar_one()
            assert row.target == f"user:{andi.id}"
            assert "Berapa cuti" not in repr(row.details) and "andi@demo" not in repr(row.details)
            assert row.details["conversations"] == 1

    _migrate()
    asyncio.run(run())


def test_erase_requires_a_disabled_user():
    async def run():
        from e2eai.core.errors import AppError
        from e2eai.data_subject import erase_subject_data
        from e2eai.db import sessions

        async with sessions()() as s:
            owner, andi, _, _ = await _setup(s)
            with pytest.raises(AppError) as e:
                await erase_subject_data(s, admin=owner, subject_id=andi.id)
            assert e.value.status == 409

    _migrate()
    asyncio.run(run())


def test_erase_deletes_content_pseudonymises_profile_and_keeps_audit_and_other_users():
    async def run():
        from e2eai.data_subject import erase_subject_data
        from e2eai.db import AuditEntry, Conversation, Message, Notification, User, UserMemory, sessions

        async with sessions()() as s:
            owner, andi, budi, _ = await _setup(s)
            audit_before = await s.scalar(select(func.count()).select_from(AuditEntry))
            andi.status = "disabled"
            await s.commit()
            result = await erase_subject_data(s, admin=owner, subject_id=andi.id)
            assert result["conversations_deleted"] == 1 and result["messages_deleted"] == 2
            assert result["memories_deleted"] == 1 and result["notifications_deleted"] == 1
            assert await s.scalar(select(func.count()).select_from(Conversation).where(Conversation.user_id == andi.id)) == 0
            assert await s.scalar(select(func.count()).select_from(UserMemory).where(UserMemory.user_id == andi.id)) == 0
            assert await s.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == andi.id)) == 0
            await s.refresh(andi)
            assert andi.email != "andi@demo.e2eai" and andi.email.endswith("@erased.invalid")
            assert andi.display_name == "Erased user" and andi.status == "disabled"
            # Budi untouched, audit log only grew
            assert await s.scalar(select(func.count()).select_from(Message)) == 1
            assert (await s.get(User, budi.id)).email == "budi@demo.e2eai"
            assert await s.scalar(select(func.count()).select_from(AuditEntry)) > audit_before
            row = (await s.execute(select(AuditEntry).where(AuditEntry.action == "dsr.erase")
                                   .order_by(AuditEntry.seq.desc()).limit(1))).scalar_one()
            assert "andi@demo" not in repr(row.details)
            assert result["audit_log"] == "retained"
            andi.email, andi.display_name, andi.status = "andi@demo.e2eai", "Andi", "active"  # restore shared demo data
            await s.commit()

    _migrate()
    asyncio.run(run())


def test_erase_is_blocked_by_legal_hold_on_chat_or_document():
    async def run():
        from e2eai.core.errors import AppError
        from e2eai.data_subject import erase_subject_data
        from e2eai.db import Conversation, Message, sessions

        async with sessions()() as s:
            owner, andi, _, conv = await _setup(s)
            andi.status = "disabled"
            (await s.get(Conversation, conv.id)).legal_hold = True
            await s.commit()
            with pytest.raises(AppError) as e:
                await erase_subject_data(s, admin=owner, subject_id=andi.id)
            assert e.value.status == 409 and "legal hold" in e.value.detail.lower()
            assert await s.scalar(select(func.count()).select_from(Message).where(Message.conversation_id == conv.id)) == 2

    _migrate()
    asyncio.run(run())


def test_routes_are_registered():
    from e2eai.main import create_app

    paths = create_app().openapi()["paths"]
    assert "get" in paths["/api/v1/privacy/subjects/{user_id}/export"]
    assert "post" in paths["/api/v1/privacy/subjects/{user_id}/erase"]
