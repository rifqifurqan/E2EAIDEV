"""FR-D8 document review owner / review date / expiry lifecycle.

Expired documents are excluded from retrieval (inside the SQL filter, so no existence hints);
documents past their review date are reported to the review owner; marking a document reviewed
moves the review date forward and audits the action with safe metadata only.
"""

import asyncio
import subprocess
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select

from e2eai.authz import principals
from e2eai.core.errors import AppError
from e2eai.db import (
    AuditEntry, Chunk, ChunkEmbedding, DocPrincipal, Document, DocumentVersion, Folder, User, sessions,
)
from e2eai.documents import LocalObjectStorage, create_uploaded_document, share_document, visible_chunks
from e2eai.ingest import ingest_version
from e2eai.retrieval import answer_question
from e2eai.seed import seed_demo

REVENUE = "The WhatsApp partnership revenue share is 30 percent."
QUESTION = "What is the revenue share in the WhatsApp partnership?"


class RecordingAuthz:
    async def write(self, writes=(), deletes=()):
        return None


class FakeEmbedder:
    model = "fake-embedding-v1"

    async def embed(self, texts):
        return [[float(len(t)), 1.0] for t in texts]


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


async def _reset(session):
    await session.execute(delete(AuditEntry).where(AuditEntry.action.like("document.lifecycle.%")))
    for model in (ChunkEmbedding, DocPrincipal, Chunk, DocumentVersion, Document, Folder):
        await session.execute(delete(model))
    await session.commit()


async def _seed(session, tmp_path):
    await seed_demo(session, password="TestPassword_123456789")
    owner = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))
    andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
    storage = LocalObjectStorage(tmp_path / "objects")
    doc = await create_uploaded_document(
        session, owner=owner, title="deal.txt", data=REVENUE.encode(), mime="text/plain", storage=storage
    )
    await ingest_version(session, embedder=FakeEmbedder(), version_id=doc.current_version_id, storage=storage)
    await share_document(session, RecordingAuthz(), actor=owner, document_id=doc.id, principal=f"user:{andi.id}")
    return owner, andi, doc


def test_expired_document_is_excluded_from_retrieval_and_restored_when_extended(tmp_path):
    async def run():
        from e2eai.doc_lifecycle import set_document_lifecycle

        async with sessions()() as session:
            await _reset(session)
            owner, andi, doc = await _seed(session, tmp_path)
            assert (await answer_question(session, embedder=FakeEmbedder(), user=andi, question=QUESTION))["citations"]

            past = datetime.now(UTC) - timedelta(days=1)
            await set_document_lifecycle(session, actor=owner, document_id=doc.id, expires_at=past)
            assert await visible_chunks(session, await principals(session, andi)) == []
            after = await answer_question(session, embedder=FakeEmbedder(), user=andi, question=QUESTION)
            assert after["citations"] == []
            assert "30 percent" not in after["answer"] and "WhatsApp" not in after["answer"]

            future = datetime.now(UTC) + timedelta(days=30)
            await set_document_lifecycle(session, actor=owner, document_id=doc.id, expires_at=future)
            assert (await answer_question(session, embedder=FakeEmbedder(), user=andi, question=QUESTION))["citations"]

    _migrate()
    asyncio.run(run())


def test_review_due_report_and_mark_reviewed_with_safe_audit(tmp_path):
    async def run():
        from e2eai.doc_lifecycle import list_due_reviews, mark_reviewed, set_document_lifecycle

        async with sessions()() as session:
            await _reset(session)
            owner, andi, doc = await _seed(session, tmp_path)
            now = datetime.now(UTC)
            await set_document_lifecycle(
                session, actor=owner, document_id=doc.id, review_owner_id=andi.id,
                review_at=now - timedelta(days=2), expires_at=now + timedelta(days=90),
            )

            due = await list_due_reviews(session, review_owner_id=andi.id)
            assert [d["document_id"] for d in due] == [str(doc.id)]
            assert due[0]["title"] == "deal.txt"
            assert due[0]["overdue_days"] >= 2
            assert "text" not in due[0] and "content" not in due[0]
            assert await list_due_reviews(session, review_owner_id=owner.id) == []

            # only the review owner (or document owner) may mark reviewed
            outsider = await session.scalar(select(User).where(func.lower(User.email) == "budi@demo.e2eai"))
            with pytest.raises(AppError) as exc:
                await mark_reviewed(session, actor=outsider, document_id=doc.id, next_review_in_days=180)
            assert exc.value.status == 403

            updated = await mark_reviewed(session, actor=andi, document_id=doc.id, next_review_in_days=180)
            assert updated.review_at > now + timedelta(days=170)
            assert await list_due_reviews(session, review_owner_id=andi.id) == []

            audits = (await session.execute(
                select(AuditEntry).where(AuditEntry.action.like("document.lifecycle.%")).order_by(AuditEntry.seq)
            )).scalars().all()
            assert [a.action for a in audits] == ["document.lifecycle.set", "document.lifecycle.reviewed"]
            for audit in audits:
                assert set(audit.details) <= {"review_owner_id", "review_at", "expires_at", "next_review_in_days"}
                assert "deal.txt" not in str(audit.details)

    _migrate()
    asyncio.run(run())


def test_lifecycle_validation_and_routes_are_wired(tmp_path):
    async def run():
        from e2eai.doc_lifecycle import set_document_lifecycle

        async with sessions()() as session:
            await _reset(session)
            owner, andi, doc = await _seed(session, tmp_path)
            now = datetime.now(UTC)
            with pytest.raises(AppError) as exc:  # expiry before review date is incoherent
                await set_document_lifecycle(
                    session, actor=owner, document_id=doc.id,
                    review_at=now + timedelta(days=30), expires_at=now + timedelta(days=5),
                )
            assert exc.value.status == 400

    _migrate()
    asyncio.run(run())

    from e2eai.main import app

    paths = app.openapi()["paths"]
    assert "put" in paths["/api/v1/documents/{document_id}/lifecycle"]
    assert "post" in paths["/api/v1/documents/{document_id}/lifecycle/reviewed"]
    assert "get" in paths["/api/v1/documents/reviews/due"]
