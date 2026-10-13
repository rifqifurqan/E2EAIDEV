"""NFR-20 cursor pagination on flywheel, AI inventory, model registry and legal-hold lists.

Cursors are not authorization tokens: admin/ownership checks still run before every page.
"""

import asyncio
import subprocess

import pytest
from sqlalchemy import delete, func, select

from e2eai.core.errors import AppError
from e2eai.db import AuditEntry, User, sessions
from e2eai.seed import ADMIN_EMAIL, bootstrap_admin, seed_demo


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


async def _people(session):
    await seed_demo(session, password="TestPassword_123456789")
    await bootstrap_admin(session, password="TestPassword_123456789")
    admin = await session.scalar(select(User).where(func.lower(User.email) == ADMIN_EMAIL))
    andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
    return admin, andi


def _walk(fetch, limit):
    """Follow cursors until exhausted; return list of pages (each a list of ids)."""
    async def run():
        pages, cursor = [], None
        for _ in range(20):
            ids, cursor = await fetch(limit, cursor)
            pages.append(ids)
            if cursor is None:
                break
        return pages
    return run()


def test_flywheel_queue_page_walks_all_items_newest_first_and_stays_admin_only():
    async def run():
        from e2eai.db import FlywheelItem
        from e2eai.flywheel import flag_answer, queue_page

        async with sessions()() as session:
            await session.execute(delete(AuditEntry).where(AuditEntry.action.like("flywheel.%")))
            await session.execute(delete(FlywheelItem))
            await session.commit()
            admin, andi = await _people(session)
            for n in range(5):
                await flag_answer(session, actor=admin, source="reviewer_flag", question=f"Q{n}")

            async def fetch(limit, cursor):
                items, nxt = await queue_page(session, actor=admin, limit=limit, cursor=cursor)
                return [i["id"] for i in items], nxt

            pages = await _walk(fetch, 2)
            assert [len(p) for p in pages] == [2, 2, 1]
            flat = [i for p in pages for i in p]
            assert len(flat) == len(set(flat)) == 5

            items, _ = await queue_page(session, actor=admin, status="dismissed")
            assert items == []

            with pytest.raises(AppError) as exc:  # a cursor never replaces the admin check
                await queue_page(session, actor=andi, limit=2)
            assert exc.value.status == 403

            with pytest.raises(AppError) as exc:
                await queue_page(session, actor=admin, cursor="not-a-cursor")
            assert exc.value.status == 422

    _migrate()
    asyncio.run(run())


def test_ai_inventory_page_walks_all_entries_and_filters_kind():
    async def run():
        from e2eai.ai_inventory import list_inventory_page, upsert_inventory_entry
        from e2eai.db import AIInventoryEntry

        async with sessions()() as session:
            await session.execute(delete(AIInventoryEntry))
            await session.commit()
            admin, andi = await _people(session)
            for n in range(5):
                await upsert_inventory_entry(session, actor=andi, kind="model", name=f"m-{n}", risk_tier="limited")

            async def fetch(limit, cursor):
                rows, nxt = await list_inventory_page(session, kind="model", limit=limit, cursor=cursor)
                return [str(r.id) for r in rows], nxt

            pages = await _walk(fetch, 2)
            assert [len(p) for p in pages] == [2, 2, 1]
            flat = [i for p in pages for i in p]
            assert len(set(flat)) == 5

            rows, nxt = await list_inventory_page(session, kind="bot")
            assert rows == [] and nxt is None
            with pytest.raises(AppError) as exc:
                await list_inventory_page(session, kind="widget")
            assert exc.value.status == 400

    _migrate()
    asyncio.run(run())


def test_model_registry_page_walks_all_versions_and_filters_name():
    async def run():
        from e2eai.db import ModelRegistryEntry
        from e2eai.model_registry import list_models_page, register_model_version

        async with sessions()() as session:
            await session.execute(delete(AuditEntry).where(AuditEntry.action.like("model_registry.%")))
            await session.execute(delete(ModelRegistryEntry))
            await session.commit()
            admin, andi = await _people(session)
            for n in range(4):
                await register_model_version(session, actor=andi, name="a", version=str(n))
            await register_model_version(session, actor=andi, name="b", version="1")

            async def fetch(limit, cursor):
                rows, nxt = await list_models_page(session, limit=limit, cursor=cursor)
                return [f'{r["name"]}@{r["version"]}' for r in rows], nxt

            pages = await _walk(fetch, 2)
            assert [len(p) for p in pages] == [2, 2, 1]
            flat = [i for p in pages for i in p]
            assert len(set(flat)) == 5

            rows, nxt = await list_models_page(session, name="b")
            assert [r["name"] for r in rows] == ["b"] and nxt is None

    _migrate()
    asyncio.run(run())


def test_legal_hold_page_walks_held_documents_and_conversations_separately(tmp_path):
    async def run():
        from e2eai.chat import create_conversation
        from e2eai.db import Conversation, Document
        from e2eai.legal_hold import list_holds_page, set_conversation_hold, set_document_hold
        from e2eai.documents import LocalObjectStorage, create_uploaded_document

        async with sessions()() as session:
            await session.execute(delete(AuditEntry).where(AuditEntry.action.like("legal_hold.%")))
            await session.commit()
            admin, andi = await _people(session)
            storage = LocalObjectStorage(tmp_path / "objects")
            held_docs, held_convs = set(), set()
            for n in range(3):
                d = await create_uploaded_document(
                    session, owner=andi, title=f"hold-{n}.txt", data=f"x{n}".encode(), mime="text/plain", storage=storage
                )
                await set_document_hold(session, actor=admin, document_id=d.id, hold=True)
                held_docs.add(str(d.id))
                c = await create_conversation(session, user=andi, title=f"hold-{n}")
                await set_conversation_hold(session, actor=admin, conversation_id=c.id, hold=True)
                held_convs.add(str(c.id))

            async def fetch_docs(limit, cursor):
                out = await list_holds_page(session, kind="documents", limit=limit, cursor=cursor)
                assert set(out) == {"documents", "next_cursor"}
                return out["documents"], out["next_cursor"]

            pages = await _walk(fetch_docs, 2)
            assert len(pages[0]) == 2 and len(pages) >= 2  # 3+ held docs force a second page
            flat = [i for p in pages for i in p]
            assert held_docs <= set(flat) and len(flat) == len(set(flat))

            async def fetch_convs(limit, cursor):
                out = await list_holds_page(session, kind="conversations", limit=limit, cursor=cursor)
                assert set(out) == {"conversations", "next_cursor"}
                return out["conversations"], out["next_cursor"]

            pages = await _walk(fetch_convs, 2)
            flat = [i for p in pages for i in p]
            assert held_convs <= set(flat) and len(flat) == len(set(flat))

            with pytest.raises(AppError) as exc:
                await list_holds_page(session, kind="emails")
            assert exc.value.status == 400

    _migrate()
    asyncio.run(run())


def test_list_routes_accept_limit_and_cursor():
    from e2eai.main import app

    paths = app.openapi()["paths"]
    for path in (
        "/api/v1/improve/flywheel", "/api/v1/governance/ai-inventory",
        "/api/v1/model-registry", "/api/v1/legal-hold",
    ):
        names = {p["name"] for p in paths[path]["get"].get("parameters", [])}
        assert {"limit", "cursor"} <= names, path
