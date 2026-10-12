"""FR-D10 dataset/index lineage.

Every index version records its source document/version, parser, chunker, and embedding model.
Lineage is written at ingest (idempotent per version+model) and is only visible to users who can
see the document, so it never leaks the existence of restricted documents.
"""

import asyncio
import subprocess

from sqlalchemy import delete, func, select

from e2eai.db import (
    Chunk, ChunkEmbedding, DocPrincipal, Document, DocumentVersion, Folder, User, sessions,
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


class OtherEmbedder(FakeEmbedder):
    model = "fake-embedding-v2"


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


async def _reset(session):
    from e2eai.db import IndexLineage

    await session.execute(delete(IndexLineage))
    for model in (ChunkEmbedding, DocPrincipal, Chunk, DocumentVersion, Document, Folder):
        await session.execute(delete(model))
    await session.commit()


async def _users(session):
    await seed_demo(session, password="TestPassword_123456789")
    owner = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))
    andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
    budi = await session.scalar(select(User).where(func.lower(User.email) == "budi@demo.e2eai"))
    return owner, andi, budi


def test_ingest_records_lineage_and_reindex_adds_new_embedding_model_without_duplicates(tmp_path):
    async def run():
        from e2eai.db import IndexLineage
        from e2eai.index_lineage import lineage_for_document

        async with sessions()() as session:
            await _reset(session)
            owner, andi, budi = await _users(session)
            storage = LocalObjectStorage(tmp_path / "objects")
            doc = await create_uploaded_document(
                session, owner=owner, title="deal.txt", data=b"Revenue share is 30 percent.",
                mime="text/plain", storage=storage,
            )
            await ingest_version(session, embedder=FakeEmbedder(), version_id=doc.current_version_id, storage=storage)
            await ingest_version(session, embedder=FakeEmbedder(), version_id=doc.current_version_id, storage=storage)

            rows = (await session.execute(select(IndexLineage))).scalars().all()
            assert len(rows) == 1  # idempotent per (version, embedding model)
            row = rows[0]
            assert row.document_id == doc.id
            assert row.version_id == doc.current_version_id
            assert row.embedding_model == "fake-embedding-v1"
            assert row.parser == "TextMarkdownParser"
            assert row.chunker == "structure-aware"
            assert row.chunk_count >= 1

            await ingest_version(session, embedder=OtherEmbedder(), version_id=doc.current_version_id, storage=storage)
            lineage = await lineage_for_document(session, doc.id)
            assert sorted(item["embedding_model"] for item in lineage) == ["fake-embedding-v1", "fake-embedding-v2"]
            for item in lineage:
                assert set(item) == {
                    "document_id", "version_id", "parser", "chunker", "embedding_model", "chunk_count", "recorded_at",
                }

    _migrate()
    asyncio.run(run())


def test_lineage_view_is_permission_filtered_without_existence_hints(tmp_path):
    async def run():
        from e2eai.index_lineage import visible_lineage

        async with sessions()() as session:
            await _reset(session)
            owner, andi, budi = await _users(session)
            storage = LocalObjectStorage(tmp_path / "objects")
            doc = await create_uploaded_document(
                session, owner=owner, title="secret-plan.txt", data=b"Top secret revenue plan.",
                mime="text/plain", storage=storage,
            )
            await ingest_version(session, embedder=FakeEmbedder(), version_id=doc.current_version_id, storage=storage)
            await share_document(session, RecordingAuthz(), actor=owner, document_id=doc.id, principal=f"user:{andi.id}")

            assert [i["document_id"] for i in await visible_lineage(session, user=andi)] == [str(doc.id)]
            assert [i["document_id"] for i in await visible_lineage(session, user=owner)] == [str(doc.id)]
            assert await visible_lineage(session, user=budi) == []
            # asking for a specific restricted document is indistinguishable from a missing one
            assert await visible_lineage(session, user=budi, document_id=doc.id) == []

            payload = str(await visible_lineage(session, user=andi))
            assert "secret-plan" not in payload and "Top secret" not in payload

    _migrate()
    asyncio.run(run())


def test_lineage_summary_counts_by_embedding_model_and_route_is_wired(tmp_path):
    async def run():
        from e2eai.index_lineage import lineage_summary

        async with sessions()() as session:
            await _reset(session)
            owner, andi, budi = await _users(session)
            storage = LocalObjectStorage(tmp_path / "objects")
            doc = await create_uploaded_document(
                session, owner=owner, title="a.txt", data=b"alpha beta", mime="text/plain", storage=storage
            )
            await ingest_version(session, embedder=FakeEmbedder(), version_id=doc.current_version_id, storage=storage)
            await ingest_version(session, embedder=OtherEmbedder(), version_id=doc.current_version_id, storage=storage)
            summary = await lineage_summary(session)
            assert summary["index_versions"] == 2
            assert summary["by_embedding_model"] == {"fake-embedding-v1": 1, "fake-embedding-v2": 1}
            assert "a.txt" not in str(summary)

    _migrate()
    asyncio.run(run())

    from e2eai.main import app

    paths = app.openapi()["paths"]
    assert "get" in paths["/api/v1/lineage"]
    assert "get" in paths["/api/v1/lineage/summary"]
