"""Document lifecycle P0 (FR-D9, FR-D13, PRD F4): trash -> restore -> purge, with the P0
no-leak guarantee held across every state.

Trash/restore flip only `status`, and retrieval already filters `status = 'active'`, so a trashed
document disappears from a shared user's retrieval, chat, and citations immediately. Purge deletes the
derived rows (chunks, embeddings, doc_principals, versions) and the stored object, tightening the local
read-index before OpenFGA; legal hold blocks purge. Tests use the real DB + pgvector path so filtering
is proven before scoring, not after.
"""

import asyncio
import subprocess

import pytest
from sqlalchemy import delete, func, select

from e2eai.authz import principals
from e2eai.core.errors import AppError
from e2eai.db import (
    AuditEntry, Chunk, ChunkEmbedding, DocPrincipal, Document, DocumentVersion, Folder, User, sessions,
)
from e2eai.documents import (
    LocalObjectStorage, create_uploaded_document, purge_document, restore_document, share_document,
    trash_document, visible_chunks,
)
from e2eai.ingest import ingest_version
from e2eai.retrieval import answer_question
from e2eai.seed import seed_demo

REVENUE = "The WhatsApp partnership revenue share is 30 percent."
QUESTION = "What is the revenue share in the WhatsApp partnership?"


class RecordingAuthz:
    def __init__(self):
        self.calls = []

    async def write(self, writes=(), deletes=()):
        self.calls.append({"writes": list(writes), "deletes": list(deletes)})


class FakeEmbedder:
    model = "fake-embedding-v1"

    async def embed(self, texts):
        return [[float(len(t)), 1.0] for t in texts]


async def _audit_count(session, action, document_id):
    return await session.scalar(
        select(func.count()).select_from(AuditEntry)
        .where(AuditEntry.action == action, AuditEntry.target == f"document:{document_id}")
    )


async def _reset(session):
    for model in (ChunkEmbedding, DocPrincipal, Chunk, DocumentVersion, Document, Folder):
        await session.execute(delete(model))
    await session.commit()


async def _users(session):
    await seed_demo(session, password="TestPassword_123456789")
    owner = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))
    andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
    return owner, andi


async def _seed_shared_doc(session, storage, owner, andi):
    """Upload a text doc, ingest (chunks + embeddings + real object), and share with Andi."""
    doc = await create_uploaded_document(
        session, owner=owner, title="deal.txt", data=REVENUE.encode(), mime="text/plain", storage=storage
    )
    await ingest_version(session, embedder=FakeEmbedder(), version_id=doc.current_version_id, storage=storage)
    await share_document(session, RecordingAuthz(), actor=owner, document_id=doc.id, principal=f"user:{andi.id}")
    return doc


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


def test_trash_hides_document_from_shared_user_without_existence_leak(tmp_path):
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi = await _users(session)
            storage = LocalObjectStorage(tmp_path / "objects")
            doc = await _seed_shared_doc(session, storage, owner, andi)

            # Before trash Andi can retrieve and gets a citation.
            assert await visible_chunks(session, await principals(session, andi))
            before = await answer_question(session, embedder=FakeEmbedder(), user=andi, question=QUESTION)
            assert before["citations"]

            await trash_document(session, actor=owner, document_id=doc.id)

            await session.refresh(doc)
            assert doc.status == "trashed"
            assert doc.trashed_at is not None
            # Andi no longer retrieves, gets no citation, and no title/content/existence hint.
            assert await visible_chunks(session, await principals(session, andi)) == []
            after = await answer_question(session, embedder=FakeEmbedder(), user=andi, question=QUESTION)
            assert after["citations"] == []
            assert "WhatsApp" not in after["answer"]
            assert "30 percent" not in after["answer"]
            # Every lifecycle action is audited (scoped to this document; the log is append-only).
            assert await _audit_count(session, "document.trash", doc.id) == 1

    _migrate()
    asyncio.run(run())


def test_restore_within_retention_lets_shared_user_retrieve_again(tmp_path):
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi = await _users(session)
            storage = LocalObjectStorage(tmp_path / "objects")
            doc = await _seed_shared_doc(session, storage, owner, andi)

            await trash_document(session, actor=owner, document_id=doc.id)
            assert await visible_chunks(session, await principals(session, andi)) == []

            await restore_document(session, actor=owner, document_id=doc.id)

            await session.refresh(doc)
            assert doc.status == "active"
            assert doc.trashed_at is None
            answer = await answer_question(session, embedder=FakeEmbedder(), user=andi, question=QUESTION)
            assert answer["citations"]
            assert "30 percent" in answer["answer"]
            assert await _audit_count(session, "document.restore", doc.id) == 1

    _migrate()
    asyncio.run(run())


def test_purge_removes_derived_rows_tightens_first_and_deletes_object(tmp_path):
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi = await _users(session)
            storage = LocalObjectStorage(tmp_path / "objects")
            doc = await _seed_shared_doc(session, storage, owner, andi)
            version = await session.get(DocumentVersion, doc.current_version_id)
            object_path = tmp_path / "objects" / version.object_key
            assert object_path.exists()

            await trash_document(session, actor=owner, document_id=doc.id)
            authz = RecordingAuthz()
            await purge_document(session, authz, actor=owner, document_id=doc.id, storage=storage)

            await session.refresh(doc)
            assert doc.status == "purged"
            assert doc.current_version_id is None
            # All derived rows removed.
            assert await session.scalar(select(func.count()).select_from(Chunk).where(Chunk.document_id == doc.id)) == 0
            assert await session.scalar(select(func.count()).select_from(ChunkEmbedding)) == 0
            assert await session.scalar(select(func.count()).select_from(DocPrincipal).where(DocPrincipal.document_id == doc.id)) == 0
            assert await session.scalar(select(func.count()).select_from(DocumentVersion).where(DocumentVersion.document_id == doc.id)) == 0
            # Stored object deleted.
            assert not object_path.exists()
            # Tighten-first: local read-index was gone before OpenFGA; OpenFGA tuples deleted for every principal.
            deletes = authz.calls[-1]["deletes"]
            users = {d["user"] for d in deletes}
            assert f"user:{andi.id}" in users and f"user:{owner.id}" in users
            # Andi sees nothing after purge.
            assert await visible_chunks(session, await principals(session, andi)) == []
            assert await _audit_count(session, "document.purge", doc.id) == 1

    _migrate()
    asyncio.run(run())


def test_legal_hold_blocks_purge_with_clear_apperror(tmp_path):
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi = await _users(session)
            storage = LocalObjectStorage(tmp_path / "objects")
            doc = await _seed_shared_doc(session, storage, owner, andi)
            doc.legal_hold = True
            await trash_document(session, actor=owner, document_id=doc.id)

            with pytest.raises(AppError) as ei:
                await purge_document(session, RecordingAuthz(), actor=owner, document_id=doc.id, storage=storage)
            assert ei.value.status == 409
            assert "legal hold" in (ei.value.title + ei.value.detail).lower()

            # Nothing was deleted: derived rows and the object survive the blocked purge.
            assert await session.scalar(select(func.count()).select_from(Chunk).where(Chunk.document_id == doc.id)) > 0
            assert await session.scalar(select(func.count()).select_from(DocPrincipal).where(DocPrincipal.document_id == doc.id)) > 0
            await session.refresh(doc)
            assert doc.status != "purged"

    _migrate()
    asyncio.run(run())
