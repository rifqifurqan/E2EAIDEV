"""FR-D9 + FR-R3: purges whose external-store delete failed are retried by an admin-only, idempotent reconcile."""

import asyncio
import subprocess

import pytest
from sqlalchemy import delete, func, select

from e2eai.core.errors import AppError
from e2eai.db import (
    AuditEntry, Chunk, ChunkEmbedding, DocPrincipal, Document, DocumentVersion, Folder, User, sessions,
)
from e2eai.documents import LocalObjectStorage, create_uploaded_document, purge_document, trash_document
from e2eai.ingest import ingest_version
from e2eai.seed import ADMIN_EMAIL, bootstrap_admin, seed_demo
from e2eai.vector_store import InMemoryVectorStore


class Embedder:
    model = "fake-reconcile-v1"

    async def embed(self, texts):
        return [[float(len(t)), 1.0] for t in texts]


class Authz:
    async def write(self, writes=(), deletes=()):
        return None


class FlakyStore(InMemoryVectorStore):
    def __init__(self):
        super().__init__()
        self.down = False
        self.delete_calls = 0

    async def delete_documents(self, document_ids):
        self.delete_calls += 1
        if self.down:
            raise AppError(503, "Upstream service unavailable", "secret-host:6333", "upstream-unavailable")
        await super().delete_documents(document_ids)


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


async def _setup(tmp_path, store):
    async with sessions()() as session:
        await session.execute(delete(AuditEntry).where(AuditEntry.action.in_(["vector_store.purge_retry"])))
        for model in (ChunkEmbedding, DocPrincipal, Chunk, DocumentVersion, Document, Folder):
            await session.execute(delete(model))
        await session.commit()
        await seed_demo(session, password="TestPassword_123456789")
        await bootstrap_admin(session, password="TestPassword_123456789")
        owner = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))
        storage = LocalObjectStorage(tmp_path / "objects")
        doc = await create_uploaded_document(session, owner=owner, title="a.txt", data=b"leave is 12 days",
                                             mime="text/plain", storage=storage)
        await ingest_version(session, embedder=Embedder(), version_id=doc.current_version_id, storage=storage,
                             vector_store=store)
        await trash_document(session, actor=owner, document_id=doc.id)
        store.down = True
        await purge_document(session, Authz(), actor=owner, document_id=doc.id, storage=storage, vector_store=store)
        store.down = False
        return owner, doc.id


def test_reconcile_retries_failed_purge_once_and_is_idempotent(tmp_path):
    from e2eai.vector_reconcile import reconcile_failed_purges

    _migrate()

    async def run():
        store = FlakyStore()
        owner, doc_id = await _setup(tmp_path, store)
        assert len(store._points) == 1  # leftover vector from the failed purge
        async with sessions()() as session:
            admin = await session.scalar(select(User).where(func.lower(User.email) == ADMIN_EMAIL))
            # The audit log is append-only and shared: purges flagged by earlier tests are legitimately pending too.
            result = await reconcile_failed_purges(session, actor=admin, vector_store=store)
            assert result["retried"] >= 1 and result["ok"] == result["retried"] and result["failed"] == 0
            assert store._points == {}
            entry = await session.scalar(select(AuditEntry).where(
                AuditEntry.action == "vector_store.purge_retry", AuditEntry.target == f"document:{doc_id}"))
            assert entry.details == {"result": "ok"}
            calls = store.delete_calls
            again = await reconcile_failed_purges(session, actor=admin, vector_store=store)
            assert again == {"retried": 0, "ok": 0, "failed": 0} and store.delete_calls == calls  # nothing pending now

    asyncio.run(run())


def test_reconcile_keeps_failing_documents_pending_without_leaking_error_text(tmp_path):
    from e2eai.vector_reconcile import reconcile_failed_purges

    _migrate()

    async def run():
        store = FlakyStore()
        owner, doc_id = await _setup(tmp_path, store)
        store.down = True
        async with sessions()() as session:
            admin = await session.scalar(select(User).where(func.lower(User.email) == ADMIN_EMAIL))
            down = await reconcile_failed_purges(session, actor=admin, vector_store=store)
            assert down["retried"] >= 1 and down["failed"] == down["retried"] and down["ok"] == 0
            rows = (await session.scalars(select(AuditEntry).where(
                AuditEntry.action == "vector_store.purge_retry", AuditEntry.target == f"document:{doc_id}"))).all()
            assert [r.details for r in rows] == [{"result": "failed"}]
            assert "secret-host" not in str(rows[0].details)
            store.down = False  # a failed retry stays pending, so the next run picks it up again
            up = await reconcile_failed_purges(session, actor=admin, vector_store=store)
            assert up["retried"] == down["retried"] and up["ok"] == up["retried"] and up["failed"] == 0
            assert store._points == {}

    asyncio.run(run())


def test_reconcile_is_admin_only_and_noop_without_external_store(tmp_path):
    from e2eai.vector_reconcile import reconcile_failed_purges

    _migrate()

    async def run():
        store = FlakyStore()
        owner, _ = await _setup(tmp_path, store)
        async with sessions()() as session:
            admin = await session.scalar(select(User).where(func.lower(User.email) == ADMIN_EMAIL))
            owner = await session.get(User, owner.id)
            with pytest.raises(AppError) as exc:
                await reconcile_failed_purges(session, actor=owner, vector_store=store)
            assert exc.value.status == 403
            assert await reconcile_failed_purges(session, actor=admin, vector_store=None) == {
                "retried": 0, "ok": 0, "failed": 0}

    asyncio.run(run())
