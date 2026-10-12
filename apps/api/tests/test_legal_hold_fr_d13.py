"""FR-D13 legal hold for documents and chats, overriding retention.

Held conversations cannot be deleted (by the user or by the retention sweep); held documents are
never purge-eligible. Only admins can place or release holds. Audit stores only ids/flags.
"""

import asyncio
import subprocess
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select, update

from e2eai.core.errors import AppError
from e2eai.db import (
    AuditEntry, Chunk, ChunkEmbedding, Conversation, DocPrincipal, Document, DocumentVersion, Folder,
    Message, MessageCitation, MessageFeedback, User, sessions,
)
from e2eai.documents import LocalObjectStorage, create_uploaded_document, trash_document
from e2eai.seed import ADMIN_EMAIL, bootstrap_admin, seed_demo


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


async def _reset(session):
    await session.execute(delete(AuditEntry).where(AuditEntry.action.like("legal_hold.%")))
    for model in (MessageFeedback, MessageCitation, Message, Conversation,
                  ChunkEmbedding, DocPrincipal, Chunk, DocumentVersion, Document, Folder):
        await session.execute(delete(model))
    await session.commit()


async def _people(session):
    await seed_demo(session, password="TestPassword_123456789")
    await bootstrap_admin(session, password="TestPassword_123456789")
    admin = await session.scalar(select(User).where(func.lower(User.email) == ADMIN_EMAIL))
    owner = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))
    return admin, owner


def test_only_admin_can_hold_and_held_chat_cannot_be_deleted(tmp_path):
    async def run():
        from e2eai.chat import create_conversation, delete_conversation
        from e2eai.legal_hold import set_conversation_hold

        async with sessions()() as session:
            await _reset(session)
            admin, owner = await _people(session)
            conv = await create_conversation(session, user=owner, title="Q3 dispute")

            with pytest.raises(AppError) as exc:
                await set_conversation_hold(session, actor=owner, conversation_id=conv.id, hold=True, reason="x")
            assert exc.value.status == 403

            await set_conversation_hold(session, actor=admin, conversation_id=conv.id, hold=True, reason="litigation 42")
            with pytest.raises(AppError) as exc:
                await delete_conversation(session, user=owner, conversation_id=conv.id)
            assert exc.value.status == 409
            assert await session.get(Conversation, conv.id) is not None

            await set_conversation_hold(session, actor=admin, conversation_id=conv.id, hold=False)
            await delete_conversation(session, user=owner, conversation_id=conv.id)
            assert await session.get(Conversation, conv.id) is None

            audits = (await session.execute(
                select(AuditEntry).where(AuditEntry.action.like("legal_hold.%")).order_by(AuditEntry.seq)
            )).scalars().all()
            assert [a.action for a in audits] == ["legal_hold.conversation.set", "legal_hold.conversation.set"]
            assert [a.details["hold"] for a in audits] == [True, False]
            for a in audits:
                assert set(a.details) <= {"hold", "reason_given"}
                assert "litigation" not in str(a.details) and "dispute" not in str(a.details)

    _migrate()
    asyncio.run(run())


def test_retention_sweep_deletes_expired_chats_but_skips_held_and_reports_held_documents(tmp_path):
    async def run():
        from e2eai.chat import create_conversation
        from e2eai.legal_hold import retention_sweep, set_conversation_hold, set_document_hold

        async with sessions()() as session:
            await _reset(session)
            admin, owner = await _people(session)
            old = await create_conversation(session, user=owner, title="old")
            held = await create_conversation(session, user=owner, title="old held")
            fresh = await create_conversation(session, user=owner, title="fresh")
            long_ago = datetime.now(UTC) - timedelta(days=400)
            await session.execute(update(Conversation).where(Conversation.id.in_([old.id, held.id])).values(updated_at=long_ago))
            await session.commit()
            await set_conversation_hold(session, actor=admin, conversation_id=held.id, hold=True)

            storage = LocalObjectStorage(tmp_path / "objects")
            doc_free = await create_uploaded_document(session, owner=owner, title="a.txt", data=b"a", mime="text/plain", storage=storage)
            doc_held = await create_uploaded_document(session, owner=owner, title="b.txt", data=b"b", mime="text/plain", storage=storage)
            for d in (doc_free, doc_held):
                await trash_document(session, actor=owner, document_id=d.id)
            await session.execute(update(Document).where(Document.id.in_([doc_free.id, doc_held.id])).values(trashed_at=long_ago))
            await session.commit()
            await set_document_hold(session, actor=admin, document_id=doc_held.id, hold=True, reason="audit")

            dry = await retention_sweep(session, chats_days=365, trash_days=30, dry_run=True)
            assert dry["chats_deleted"] == 0 and dry["chats_due"] == 1
            assert dry["documents_due"] == [str(doc_free.id)]
            assert dry["held_chats_skipped"] == 1 and dry["held_documents_skipped"] == 1
            assert await session.get(Conversation, old.id) is not None

            purged: list[uuid.UUID] = []

            async def purge(document_id):
                purged.append(document_id)

            real = await retention_sweep(session, chats_days=365, trash_days=30, purge_document_fn=purge)
            assert real["chats_deleted"] == 1
            assert await session.get(Conversation, old.id) is None
            assert await session.get(Conversation, held.id) is not None  # legal hold overrides retention
            assert await session.get(Conversation, fresh.id) is not None
            assert purged == [doc_free.id]  # held document never purged
            assert "title" not in str(real) and "old" not in str(real).replace("held", "")

    _migrate()
    asyncio.run(run())


def test_held_document_blocks_purge_and_routes_are_wired(tmp_path):
    async def run():
        from e2eai.documents import purge_document
        from e2eai.legal_hold import list_holds, set_document_hold

        class NoopAuthz:
            async def write(self, writes=(), deletes=()):
                return None

        async with sessions()() as session:
            await _reset(session)
            admin, owner = await _people(session)
            storage = LocalObjectStorage(tmp_path / "objects")
            doc = await create_uploaded_document(session, owner=owner, title="c.txt", data=b"c", mime="text/plain", storage=storage)
            with pytest.raises(AppError) as exc:
                await set_document_hold(session, actor=owner, document_id=doc.id, hold=True)
            assert exc.value.status == 403
            await set_document_hold(session, actor=admin, document_id=doc.id, hold=True)
            with pytest.raises(AppError) as exc:
                await purge_document(session, NoopAuthz(), actor=owner, document_id=doc.id, storage=storage)
            assert exc.value.status == 409
            holds = await list_holds(session)
            assert holds["documents"] == [str(doc.id)] and holds["conversations"] == []

    _migrate()
    asyncio.run(run())

    from e2eai.main import app

    paths = app.openapi()["paths"]
    assert "put" in paths["/api/v1/legal-hold/documents/{document_id}"]
    assert "put" in paths["/api/v1/legal-hold/conversations/{conversation_id}"]
    assert "get" in paths["/api/v1/legal-hold"]
    assert "post" in paths["/api/v1/legal-hold/retention-sweep"]
