"""NFR-20 cursor pagination on API-key and index-lineage lists.

Cursors are not authorization tokens: ownership (API keys) and the document permission predicate
(lineage) are applied in SQL before every page.
"""

import asyncio
import subprocess

import pytest
from sqlalchemy import delete, func, select

from e2eai.core.errors import AppError
from e2eai.db import (
    ApiKey, Chunk, ChunkEmbedding, DocPrincipal, Document, DocumentVersion, Folder, IndexLineage, User, sessions,
)
from e2eai.documents import LocalObjectStorage, create_uploaded_document, share_document
from e2eai.ingest import ingest_version
from e2eai.seed import seed_demo


class RecordingAuthz:
    async def write(self, writes=(), deletes=()):
        return None


class FakeEmbedder:
    model = "fake-embedding-v1"

    async def embed(self, texts):
        return [[float(len(t)), 1.0] for t in texts]


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


async def _users(session):
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


def test_api_key_list_page_is_owner_scoped_and_walks_all_keys():
    async def run():
        from e2eai.api_keys import create_api_key, list_api_keys_page

        async with sessions()() as session:
            await session.execute(delete(ApiKey))
            await session.commit()
            owner, andi, _ = await _users(session)
            for n in range(5):
                await create_api_key(session, user=andi, name=f"k{n}", scopes=["chat"])
            await create_api_key(session, user=owner, name="other-owner", scopes=["chat"])

            async def fetch(limit, cursor):
                rows, nxt = await list_api_keys_page(session, user=andi, limit=limit, cursor=cursor)
                for r in rows:  # no hash / raw key ever leaves
                    assert "key_hash" not in r and "key" not in r
                return [r["id"] for r in rows], nxt

            pages = await _walk(fetch, 2)
            assert [len(p) for p in pages] == [2, 2, 1]
            flat = [i for p in pages for i in p]
            assert len(flat) == len(set(flat)) == 5  # the other owner's key never appears

            # A cursor taken from andi's list cannot widen another user's list.
            _, cursor = await list_api_keys_page(session, user=andi, limit=2)
            rows, _ = await list_api_keys_page(session, user=owner, limit=50, cursor=cursor)
            assert all(r["name"] == "other-owner" for r in rows)

            with pytest.raises(AppError) as exc:
                await list_api_keys_page(session, user=andi, cursor="not-a-cursor")
            assert exc.value.status == 422

    _migrate()
    asyncio.run(run())


def test_lineage_page_walks_visible_rows_only(tmp_path):
    async def run():
        from e2eai.index_lineage import visible_lineage_page

        async with sessions()() as session:
            await session.execute(delete(IndexLineage))
            for model in (ChunkEmbedding, DocPrincipal, Chunk, DocumentVersion, Document, Folder):
                await session.execute(delete(model))
            await session.commit()
            owner, andi, budi = await _users(session)
            storage = LocalObjectStorage(tmp_path / "objects")
            authz = RecordingAuthz()
            shared_ids = set()
            for n in range(3):
                doc = await create_uploaded_document(
                    session, owner=owner, title=f"shared-{n}.txt", data=f"Shared text {n}.".encode(),
                    mime="text/plain", storage=storage,
                )
                await ingest_version(session, embedder=FakeEmbedder(), version_id=doc.current_version_id, storage=storage)
                await share_document(session, authz, actor=owner, document_id=doc.id, principal=f"user:{andi.id}", level="viewer")
                shared_ids.add(str(doc.id))
            secret = await create_uploaded_document(
                session, owner=owner, title="restricted.txt", data=b"Restricted text.", mime="text/plain", storage=storage,
            )
            await ingest_version(session, embedder=FakeEmbedder(), version_id=secret.current_version_id, storage=storage)

            async def fetch(limit, cursor):
                rows, nxt = await visible_lineage_page(session, user=andi, limit=limit, cursor=cursor)
                return [r["document_id"] for r in rows], nxt

            pages = await _walk(fetch, 2)
            assert [len(p) for p in pages] == [2, 1]
            flat = {d for p in pages for d in p}
            assert flat == shared_ids and str(secret.id) not in flat

            rows, nxt = await visible_lineage_page(session, user=budi, limit=2)
            assert rows == [] and nxt is None  # budi sees nothing, not even a cursor

            with pytest.raises(AppError) as exc:
                await visible_lineage_page(session, user=andi, cursor="not-a-cursor")
            assert exc.value.status == 422

    _migrate()
    asyncio.run(run())


def test_routes_accept_limit_and_cursor():
    from e2eai.main import app

    paths = app.openapi()["paths"]
    for path in ("/api/v1/lineage", "/api/v1/api-keys"):
        names = {p["name"] for p in paths[path]["get"].get("parameters", [])}
        assert {"limit", "cursor"} <= names, path
