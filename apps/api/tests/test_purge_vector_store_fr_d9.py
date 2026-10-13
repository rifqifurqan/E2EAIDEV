"""FR-D9 + FR-R3: trash and purge propagate to an external vector store, and a store outage never blocks the
SQL-side tightening (the SQL re-check in retrieval keeps trashed/purged chunks invisible meanwhile)."""

import asyncio
import subprocess

from sqlalchemy import delete, func, select

from e2eai.core.errors import AppError
from e2eai.db import Chunk, ChunkEmbedding, DocPrincipal, Document, DocumentVersion, Folder, User, sessions
from e2eai.documents import LocalObjectStorage, create_uploaded_document, purge_document, trash_document
from e2eai.ingest import ingest_version
from e2eai.seed import seed_demo
from e2eai.vector_store import InMemoryVectorStore, VectorQuery


class Embedder:
    model = "fake-purge-v1"

    async def embed(self, texts):
        return [[float(len(t)), 1.0] for t in texts]


class Authz:
    async def write(self, writes=(), deletes=()):
        return None


class RecordingStore(InMemoryVectorStore):
    def __init__(self, fail_delete=False):
        super().__init__()
        self.deleted: list[list[str]] = []
        self.fail_delete = fail_delete

    async def delete_documents(self, document_ids):
        ids = list(document_ids)
        if self.fail_delete:
            raise AppError(503, "Upstream service unavailable", "", "upstream-unavailable")
        self.deleted.append(ids)
        await super().delete_documents(ids)


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


async def _setup(tmp_path, store):
    async with sessions()() as session:
        for model in (ChunkEmbedding, DocPrincipal, Chunk, DocumentVersion, Document, Folder):
            await session.execute(delete(model))
        await session.commit()
        await seed_demo(session, password="TestPassword_123456789")
        owner = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))
        storage = LocalObjectStorage(tmp_path / "objects")
        doc = await create_uploaded_document(session, owner=owner, title="a.txt", data=b"leave is 12 days",
                                             mime="text/plain", storage=storage)
        await ingest_version(session, embedder=Embedder(), version_id=doc.current_version_id, storage=storage,
                             vector_store=store)
        return session, owner, doc, storage


def test_ingest_writes_to_external_store_and_purge_removes_it(tmp_path):
    _migrate()

    async def run():
        store = RecordingStore()
        async with sessions()() as s0:
            pass
        session, owner, doc, storage = await _setup(tmp_path, store)
        async with sessions()() as session:
            owner = await session.get(User, owner.id)
            assert len(store._points) == 1  # ingest indexed through the store
            await trash_document(session, actor=owner, document_id=doc.id)
            await purge_document(session, Authz(), actor=owner, document_id=doc.id, storage=storage, vector_store=store)
            assert store.deleted == [[str(doc.id)]]
            assert store._points == {}

    asyncio.run(run())


def test_store_outage_does_not_block_purge_and_is_reported_in_audit(tmp_path):
    _migrate()

    async def run():
        store = RecordingStore()
        session, owner, doc, storage = await _setup(tmp_path, store)
        store.fail_delete = True
        async with sessions()() as session:
            owner = await session.get(User, owner.id)
            await trash_document(session, actor=owner, document_id=doc.id)
            await purge_document(session, Authz(), actor=owner, document_id=doc.id, storage=storage, vector_store=store)
            refreshed = await session.get(Document, doc.id)
            assert refreshed.status == "purged"  # SQL tightening happened regardless
            assert await session.scalar(select(func.count()).select_from(Chunk).where(Chunk.document_id == doc.id)) == 0
            from e2eai.db import AuditEntry
            entry = await session.scalar(
                select(AuditEntry).where(AuditEntry.action == "document.purge", AuditEntry.target == f"document:{doc.id}")
            )
            assert entry.details.get("vector_store_purge") == "failed"
            assert "boom" not in str(entry.details)

    asyncio.run(run())


def test_purge_without_external_store_is_unchanged(tmp_path):
    _migrate()

    async def run():
        session, owner, doc, storage = await _setup(tmp_path, None)
        async with sessions()() as session:
            owner = await session.get(User, owner.id)
            await trash_document(session, actor=owner, document_id=doc.id)
            await purge_document(session, Authz(), actor=owner, document_id=doc.id, storage=storage)
            from e2eai.db import AuditEntry
            entry = await session.scalar(
                select(AuditEntry).where(AuditEntry.action == "document.purge", AuditEntry.target == f"document:{doc.id}")
            )
            assert "vector_store_purge" not in entry.details

    asyncio.run(run())
