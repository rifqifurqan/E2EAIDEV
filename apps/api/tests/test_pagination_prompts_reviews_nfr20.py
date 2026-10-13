"""NFR-20 cursor pagination on prompt versions and due document reviews.

Cursors are not authorization tokens: the review list stays scoped to the review owner in SQL and the
prompt list still requires the existing `bots` scope / existing prompt before every page.
"""

import asyncio
import subprocess
from datetime import UTC, datetime, timedelta

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


def test_prompt_version_page_walks_versions_in_order_and_rejects_bad_cursor():
    async def run():
        from e2eai.db import Prompt, PromptLabel, PromptVersion
        from e2eai.prompt_registry import add_prompt_version, create_prompt, list_prompt_versions_page

        async with sessions()() as session:
            for model in (PromptLabel, PromptVersion, Prompt):
                await session.execute(delete(model))
            await session.commit()
            owner, _, _ = await _people(session)
            prompt = await create_prompt(session, owner=owner, name="Paged", description="d")
            other = await create_prompt(session, owner=owner, name="Other", description="d")
            for n in range(5):
                await add_prompt_version(session, actor=owner, prompt_id=prompt.id, template=f"v{n} {{{{ question }}}}")
            await add_prompt_version(session, actor=owner, prompt_id=other.id, template="other {{ question }}")

            async def fetch(limit, cursor):
                rows, nxt = await list_prompt_versions_page(session, prompt_id=prompt.id, limit=limit, cursor=cursor)
                return [r["version"] for r in rows], nxt

            pages = await _walk(fetch, 2)
            assert pages == [[1, 2], [3, 4], [5]]  # the other prompt's version never appears

            with pytest.raises(AppError) as exc:
                await list_prompt_versions_page(session, prompt_id=prompt.id, cursor="not-a-cursor")
            assert exc.value.status == 422
            with pytest.raises(AppError):  # unknown prompt still fails before paging
                import uuid
                await list_prompt_versions_page(session, prompt_id=uuid.uuid4())

    _migrate()
    asyncio.run(run())


def test_due_review_page_is_review_owner_scoped_and_walks_all_documents(tmp_path):
    async def run():
        from e2eai.db import (
            AccessRequest, Chunk, ChunkEmbedding, DocPrincipal, Document, DocumentVersion, Folder, FolderPrincipal,
            Notification,
        )
        from e2eai.doc_lifecycle import list_due_reviews_page, set_document_lifecycle
        from e2eai.documents import create_seeded_document

        async with sessions()() as session:
            for model in (AccessRequest, Notification, FolderPrincipal, ChunkEmbedding, DocPrincipal,
                          Chunk, DocumentVersion, Document, Folder):
                await session.execute(delete(model))
            await session.commit()
            owner, andi, budi = await _people(session)
            now = datetime.now(UTC)
            for n in range(5):
                doc = await create_seeded_document(
                    session, owner=owner, title=f"Review Doc {n}", text=f"Doc {n} content.", page=1,
                )
                await set_document_lifecycle(
                    session, actor=owner, document_id=doc.id, review_owner_id=andi.id,
                    review_at=now - timedelta(days=10 - n), expires_at=now + timedelta(days=90),
                )

            async def fetch(limit, cursor):
                rows, nxt = await list_due_reviews_page(
                    session, review_owner_id=andi.id, limit=limit, cursor=cursor
                )
                for r in rows:
                    assert "text" not in r and "content" not in r
                return [r["title"] for r in rows], nxt

            pages = await _walk(fetch, 2)
            assert [len(p) for p in pages] == [2, 2, 1]
            flat = [t for p in pages for t in p]
            assert flat == [f"Review Doc {n}" for n in range(5)]  # most overdue first

            # A cursor from andi's list cannot widen another review owner's list.
            _, cursor = await list_due_reviews_page(session, review_owner_id=andi.id, limit=2)
            rows, nxt = await list_due_reviews_page(session, review_owner_id=budi.id, limit=50, cursor=cursor)
            assert rows == [] and nxt is None

            with pytest.raises(AppError) as exc:
                await list_due_reviews_page(session, review_owner_id=andi.id, cursor="not-a-cursor")
            assert exc.value.status == 422

    _migrate()
    asyncio.run(run())


def test_routes_accept_limit_and_cursor():
    from e2eai.main import app

    paths = app.openapi()["paths"]
    for path in ("/api/v1/documents/reviews/due", "/api/v1/prompts/{prompt_id}/versions"):
        names = {p["name"] for p in paths[path]["get"]["parameters"]}
        assert {"limit", "cursor"} <= names, path
