"""NFR-20 cursor pagination on bot approvals, document access requests and user memory lists.

Cursors are not authorization tokens: ownership (memory, access requests) and the scope check (approvals)
apply in SQL / before every page.
"""

import asyncio
import subprocess

import pytest
from sqlalchemy import delete, func, select

from e2eai.core.errors import AppError
from e2eai.db import User, sessions
from e2eai.seed import seed_demo


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


async def _people(session):
    await seed_demo(session, password="TestPassword_123456789")
    owner = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))
    andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
    budi = await session.scalar(select(User).where(func.lower(User.email) == "budi@demo.e2eai"))
    return owner, andi, budi


async def _walk(fetch, limit):
    pages, cursor = [], None
    for _ in range(20):
        ids, cursor = await fetch(limit, cursor)
        pages.append(ids)
        if cursor is None:
            break
    return pages


def test_memory_page_is_owner_scoped_and_walks_all_items():
    async def run():
        from e2eai.db import UserMemory, UserMemorySetting
        from e2eai.user_memory import list_memories_page, remember, set_enabled

        async with sessions()() as session:
            await session.execute(delete(UserMemory))
            await session.execute(delete(UserMemorySetting))
            await session.commit()
            _, andi, budi = await _people(session)
            await set_enabled(session, user=andi, enabled=True)
            await set_enabled(session, user=budi, enabled=True)
            for n in range(5):
                await remember(session, user=andi, text=f"andi memory {n}")
            await remember(session, user=budi, text="budi memory")

            async def fetch(limit, cursor):
                rows, nxt = await list_memories_page(session, user=andi, limit=limit, cursor=cursor)
                assert all("budi" not in r["text"] for r in rows)
                return [r["id"] for r in rows], nxt

            pages = await _walk(fetch, 2)
            assert [len(p) for p in pages] == [2, 2, 1]
            flat = [i for p in pages for i in p]
            assert len(flat) == len(set(flat)) == 5

            # A cursor from andi's list cannot widen budi's list.
            _, cursor = await list_memories_page(session, user=andi, limit=2)
            rows, _ = await list_memories_page(session, user=budi, limit=50, cursor=cursor)
            assert [r["text"] for r in rows] in ([], ["budi memory"])
            assert all("andi" not in r["text"] for r in rows)

            with pytest.raises(AppError) as exc:
                await list_memories_page(session, user=andi, cursor="not-a-cursor")
            assert exc.value.status == 422

    _migrate()
    asyncio.run(run())


def test_access_request_page_is_owner_scoped_and_walks_all_requests(tmp_path):
    async def run():
        from e2eai.db import (
            AccessRequest, Chunk, ChunkEmbedding, DocPrincipal, Document, DocumentVersion, Folder, FolderPrincipal,
            Notification,
        )
        from e2eai.documents import create_seeded_document, list_access_requests_page, request_access

        async with sessions()() as session:
            for model in (AccessRequest, Notification, FolderPrincipal, ChunkEmbedding, DocPrincipal,
                          Chunk, DocumentVersion, Document, Folder):
                await session.execute(delete(model))
            await session.commit()
            owner, andi, budi = await _people(session)
            docs = [
                await create_seeded_document(
                    session, owner=owner, title=f"Owner Doc {n}", text=f"Owner doc {n}.", page=1,
                )
                for n in range(3)
            ]
            for doc in docs:
                await request_access(session, requester=andi, document_id=doc.id)
                await request_access(session, requester=budi, document_id=doc.id)

            async def fetch(limit, cursor):
                rows, nxt = await list_access_requests_page(session, owner=owner, limit=limit, cursor=cursor)
                return [r.id for r in rows], nxt

            pages = await _walk(fetch, 4)
            assert [len(p) for p in pages] == [4, 2]
            flat = [i for p in pages for i in p]
            assert len(flat) == len(set(flat)) == 6

            # Andi owns nothing: an owner's cursor does not widen what Andi may see.
            _, cursor = await list_access_requests_page(session, owner=owner, limit=2)
            rows, nxt = await list_access_requests_page(session, owner=andi, limit=50, cursor=cursor)
            assert rows == [] and nxt is None

            with pytest.raises(AppError) as exc:
                await list_access_requests_page(session, owner=owner, cursor="not-a-cursor")
            assert exc.value.status == 422

    _migrate()
    asyncio.run(run())


def test_bot_approval_page_walks_all_records_and_filters_by_bot():
    async def run():
        from e2eai.bot_approval import list_bot_approvals_page, request_bot_approval
        from e2eai.bot_release import create_bot
        from e2eai.db import AIInventoryEntry, AuditEntry, Bot, BotApproval, BotRiskClassification

        async with sessions()() as session:
            await session.execute(delete(AuditEntry).where(AuditEntry.action.like("governance.bot_approval.%")))
            await session.execute(delete(BotApproval))
            await session.execute(delete(AIInventoryEntry))
            await session.execute(delete(BotRiskClassification))
            await session.execute(delete(Bot))
            await session.commit()
            owner, _, _ = await _people(session)
            bot_a = await create_bot(session, owner=owner, name="Bot A")
            bot_b = await create_bot(session, owner=owner, name="Bot B")
            for _ in range(4):
                await request_bot_approval(session, actor=owner, bot_id=bot_a.id)
            await request_bot_approval(session, actor=owner, bot_id=bot_b.id)

            async def fetch(limit, cursor):
                rows, nxt = await list_bot_approvals_page(session, limit=limit, cursor=cursor)
                return [r.id for r in rows], nxt

            pages = await _walk(fetch, 2)
            assert [len(p) for p in pages] == [2, 2, 1]
            flat = [i for p in pages for i in p]
            assert len(flat) == len(set(flat)) == 5

            only_b, nxt = await list_bot_approvals_page(session, bot_id=bot_b.id, limit=10)
            assert len(only_b) == 1 and only_b[0].bot_id == bot_b.id and nxt is None

            with pytest.raises(AppError) as exc:
                await list_bot_approvals_page(session, cursor="not-a-cursor")
            assert exc.value.status == 422

    _migrate()
    asyncio.run(run())


def test_routes_accept_limit_and_cursor():
    from e2eai.main import app

    paths = app.openapi()["paths"]
    for path in (
        "/api/v1/memory",
        "/api/v1/documents/access-requests",
        "/api/v1/governance/bot-approvals",
    ):
        names = {p["name"] for p in paths[path]["get"]["parameters"]}
        assert {"limit", "cursor"} <= names, path
