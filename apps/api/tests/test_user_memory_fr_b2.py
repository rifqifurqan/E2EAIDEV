"""FR-B2 long-term user memory: opt-in, viewable and deletable by the user, masked, private.

Deterministic/offline: no model calls. Memory text is PII-masked and secret-redacted before storage,
only the owning user can list/delete it, and audit events carry counts/ids only (never the text).
"""

import asyncio
import subprocess

import pytest
from sqlalchemy import delete, func, select


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


async def _people(session):
    from e2eai.db import User
    from e2eai.seed import seed_demo

    await seed_demo(session, password="TestPassword_123456789")
    andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
    budi = await session.scalar(select(User).where(func.lower(User.email) == "budi@demo.e2eai"))
    return andi, budi


def test_memory_is_opt_in_and_masks_pii_and_secrets():
    async def run():
        from e2eai.core.errors import AppError
        from e2eai.db import UserMemory, UserMemorySetting, sessions
        from e2eai.user_memory import list_memories, remember, set_enabled

        async with sessions()() as session:
            await session.execute(delete(UserMemory))
            await session.execute(delete(UserMemorySetting))
            await session.commit()
            andi, _ = await _people(session)

            with pytest.raises(AppError) as exc:  # off by default
                await remember(session, user=andi, text="I prefer short answers")
            assert exc.value.status == 409

            await set_enabled(session, user=andi, enabled=True)
            await remember(
                session, user=andi, text="Contact me at andi@example.com, api_key=abcd1234abcd1234abcd"
            )
            items = await list_memories(session, user=andi)
            assert len(items) == 1
            assert "andi@example.com" not in items[0]["text"]
            assert "abcd1234abcd1234abcd" not in items[0]["text"]
            assert "[EMAIL]" in items[0]["text"]

            with pytest.raises(AppError) as empty:
                await remember(session, user=andi, text="   ")
            assert empty.value.status == 400

    _migrate()
    asyncio.run(run())


def test_user_sees_and_deletes_only_own_memory_with_content_free_audit():
    async def run():
        from e2eai.core.errors import AppError
        from e2eai.db import AuditEntry, UserMemory, UserMemorySetting, sessions
        from e2eai.user_memory import clear_memories, delete_memory, list_memories, remember, set_enabled

        async with sessions()() as session:
            await session.execute(delete(UserMemory))
            await session.execute(delete(UserMemorySetting))
            await session.commit()
            andi, budi = await _people(session)
            for user in (andi, budi):
                await set_enabled(session, user=user, enabled=True)
            await remember(session, user=andi, text="Andi works on the Sales partnership deck")
            await remember(session, user=andi, text="Andi likes bullet lists")
            await remember(session, user=budi, text="Budi handles HR leave policy")

            andi_items = await list_memories(session, user=andi)
            assert len(andi_items) == 2
            assert all("Budi" not in i["text"] for i in andi_items)

            budi_items = await list_memories(session, user=budi)
            with pytest.raises(AppError) as exc:  # cannot delete someone else's memory; same 404 as missing
                await delete_memory(session, user=andi, memory_id=budi_items[0]["id"])
            assert exc.value.status == 404
            assert len(await list_memories(session, user=budi)) == 1

            await delete_memory(session, user=andi, memory_id=andi_items[0]["id"])
            assert len(await list_memories(session, user=andi)) == 1

            removed = await clear_memories(session, user=andi)
            assert removed == 1
            assert await list_memories(session, user=andi) == []
            assert len(await list_memories(session, user=budi)) == 1

            actions = {
                a.action
                for a in (await session.scalars(select(AuditEntry).where(AuditEntry.action.like("memory.%")))).all()
            }
            assert {"memory.enable", "memory.add", "memory.delete", "memory.clear"} <= actions
            blob = " ".join(
                str(a.details)
                for a in (await session.scalars(select(AuditEntry).where(AuditEntry.action.like("memory.%")))).all()
            )
            assert "bullet lists" not in blob and "partnership" not in blob

    _migrate()
    asyncio.run(run())


def test_recall_context_respects_opt_out_and_limit():
    async def run():
        from e2eai.db import UserMemory, UserMemorySetting, sessions
        from e2eai.user_memory import recall_context, remember, set_enabled

        async with sessions()() as session:
            await session.execute(delete(UserMemory))
            await session.execute(delete(UserMemorySetting))
            await session.commit()
            andi, budi = await _people(session)
            await set_enabled(session, user=andi, enabled=True)
            for i in range(5):
                await remember(session, user=andi, text=f"fact number {i}")

            recalled = await recall_context(session, user=andi, limit=3)
            assert len(recalled) == 3
            assert recalled[0] == "fact number 4"  # newest first

            assert await recall_context(session, user=budi) == []  # never opted in

            await set_enabled(session, user=andi, enabled=False)
            assert await recall_context(session, user=andi) == []  # opt-out stops recall

    _migrate()
    asyncio.run(run())


def test_chat_pipeline_uses_opted_in_long_term_memory_as_uncited_context():
    async def run():
        from e2eai.chat import create_conversation, send_message
        from e2eai.db import UserMemory, UserMemorySetting, sessions
        from e2eai.user_memory import remember, set_enabled

        class FakeEmbedder:
            model = "fake-embedding-v1"

            async def embed(self, texts):
                return [[1.0, 0.0] for _ in texts]

        class RecordingGenerator:
            def __init__(self):
                self.chunks = []

            async def generate(self, question, chunks, answer_language):
                self.chunks = chunks
                memory = next(c for c in chunks if c.get("source") == "user_memory")
                return f"remembered: {memory['text']}"

        async with sessions()() as session:
            await session.execute(delete(UserMemory))
            await session.execute(delete(UserMemorySetting))
            await session.commit()
            andi, _ = await _people(session)
            await set_enabled(session, user=andi, enabled=True)
            await remember(session, user=andi, text="Andi prefers concise bullet answers")
            conv = await create_conversation(session, user=andi, title="Memory chat")
            generator = RecordingGenerator()

            result = await send_message(
                session,
                user=andi,
                conversation_id=conv.id,
                question="How should you answer me?",
                embedder=FakeEmbedder(),
                answer_generator=generator,
                scope="this_document",
            )

            assert result["answer"] == "remembered: Andi prefers concise bullet answers"
            assert result["citations"] == []  # memory context is not a document/source citation
            assert result["memory"] == {"used": True, "count": 1}
            assert generator.chunks[0]["source"] == "user_memory"
            assert generator.chunks[0]["document"] == "User memory"

    _migrate()
    asyncio.run(run())


def test_memory_routes_are_wired():
    from e2eai.main import app

    paths = app.openapi()["paths"]
    assert "get" in paths["/api/v1/memory"] and "post" in paths["/api/v1/memory"]
    assert "delete" in paths["/api/v1/memory"]
    assert "delete" in paths["/api/v1/memory/{memory_id}"]
    assert "put" in paths["/api/v1/memory/settings"]
