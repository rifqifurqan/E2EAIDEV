"""Sensitivity labels (FR-D5) and share-policy guardrails (FR-S7, FR-M9 kin).

Labels are public/internal/confidential/restricted; upload/create defaults to internal. Guardrails
run *before* any OpenFGA tuple or doc_principal write, so a blocked share creates no grant anywhere
(only an audit row). Default admin policy is local-only (external sharing off). The DB tests use the
real DB + pgvector path so the no-leak guarantee is proven, not assumed.
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
    LocalObjectStorage, create_uploaded_document, share_document, update_sensitivity, visible_chunks,
)
from e2eai.ingest import ingest_version
from e2eai.retrieval import answer_question
from e2eai.seed import seed_demo
from e2eai.share_policy import SENSITIVITIES, SharePolicy, share_block_reason

REVENUE = "The WhatsApp partnership revenue share is 30 percent."
QUESTION = "What is the revenue share in the WhatsApp partnership?"


# --- Pure policy logic: fast, no DB (the branch check ponytail wants) ---

def test_default_policy_is_local_only():
    assert SharePolicy().allow_external is False


def test_internal_doc_to_user_is_allowed():
    assert share_block_reason("internal", "user:123", SharePolicy()) is None


def test_restricted_cannot_be_shared_company_wide():
    assert share_block_reason("restricted", "org:42", SharePolicy()) is not None
    # but a plain user share of a restricted doc is fine
    assert share_block_reason("restricted", "user:7", SharePolicy()) is None


def test_confidential_and_restricted_never_external_even_if_enabled():
    enabled = SharePolicy(allow_external=True)
    assert share_block_reason("confidential", "guest:x@ext.com", enabled) is not None
    assert share_block_reason("restricted", "guest:x@ext.com", enabled) is not None


def test_external_off_blocks_even_internal_externally():
    assert share_block_reason("internal", "guest:x@ext.com", SharePolicy()) is not None
    assert share_block_reason("internal", "guest:x@ext.com", SharePolicy(allow_external=True)) is None


# --- DB-backed tests (mirror the lifecycle suite) ---

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
    budi = await session.scalar(select(User).where(func.lower(User.email) == "budi@demo.e2eai"))
    return owner, andi, budi


async def _seed_doc(session, storage, owner):
    doc = await create_uploaded_document(
        session, owner=owner, title="deal.txt", data=REVENUE.encode(), mime="text/plain", storage=storage
    )
    await ingest_version(session, embedder=FakeEmbedder(), version_id=doc.current_version_id, storage=storage)
    return doc


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


def test_upload_defaults_to_internal_label(tmp_path):
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, _, _ = await _users(session)
            storage = LocalObjectStorage(tmp_path / "objects")
            doc = await _seed_doc(session, storage, owner)
            await session.refresh(doc)
            assert doc.sensitivity == "internal"

    _migrate()
    asyncio.run(run())


def test_allowed_user_share_creates_tuple_and_principal(tmp_path):
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi, _ = await _users(session)
            storage = LocalObjectStorage(tmp_path / "objects")
            doc = await _seed_doc(session, storage, owner)

            authz = RecordingAuthz()
            await share_document(session, authz, actor=owner, document_id=doc.id, principal=f"user:{andi.id}")

            # OpenFGA tuple written and read-index row created.
            assert authz.calls and authz.calls[0]["writes"]
            row = await session.scalar(select(DocPrincipal).where(
                DocPrincipal.document_id == doc.id, DocPrincipal.principal == f"user:{andi.id}"))
            assert row is not None
            # Andi retrieves and is cited.
            answer = await answer_question(session, embedder=FakeEmbedder(), user=andi, question=QUESTION)
            assert answer["citations"]
            assert await _audit_count(session, "document.share", doc.id) == 1

    _migrate()
    asyncio.run(run())


def test_restricted_org_wide_share_blocked_audited_no_grant(tmp_path):
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, _, budi = await _users(session)
            storage = LocalObjectStorage(tmp_path / "objects")
            doc = await _seed_doc(session, storage, owner)
            await update_sensitivity(session, actor=owner, document_id=doc.id, sensitivity="restricted")

            authz = RecordingAuthz()
            with pytest.raises(AppError) as ei:
                await share_document(session, authz, actor=owner, document_id=doc.id,
                                     principal=f"org:{budi.org_id}")
            assert ei.value.status == 403

            # No OpenFGA tuple and no doc_principal for the company-wide audience.
            assert authz.calls == []
            assert await session.scalar(select(func.count()).select_from(DocPrincipal).where(
                DocPrincipal.document_id == doc.id, DocPrincipal.principal == f"org:{budi.org_id}")) == 0
            # Blocked share is audited.
            assert await _audit_count(session, "document.share.blocked", doc.id) == 1

    _migrate()
    asyncio.run(run())


def test_confidential_external_share_blocked_audited_no_grant(tmp_path):
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, _, _ = await _users(session)
            storage = LocalObjectStorage(tmp_path / "objects")
            doc = await _seed_doc(session, storage, owner)
            await update_sensitivity(session, actor=owner, document_id=doc.id, sensitivity="confidential")

            authz = RecordingAuthz()
            # Even with external sharing enabled, confidential may never leave the org.
            with pytest.raises(AppError) as ei:
                await share_document(session, authz, actor=owner, document_id=doc.id,
                                     principal="guest:partner@external.com", policy=SharePolicy(allow_external=True))
            assert ei.value.status == 403
            assert authz.calls == []
            assert await session.scalar(select(func.count()).select_from(DocPrincipal).where(
                DocPrincipal.document_id == doc.id, DocPrincipal.principal == "guest:partner@external.com")) == 0
            assert await _audit_count(session, "document.share.blocked", doc.id) == 1

    _migrate()
    asyncio.run(run())


def test_label_update_is_audited(tmp_path):
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, _, _ = await _users(session)
            storage = LocalObjectStorage(tmp_path / "objects")
            doc = await _seed_doc(session, storage, owner)

            await update_sensitivity(session, actor=owner, document_id=doc.id, sensitivity="confidential")
            await session.refresh(doc)
            assert doc.sensitivity == "confidential"
            assert await _audit_count(session, "document.sensitivity", doc.id) == 1

            with pytest.raises(AppError):
                await update_sensitivity(session, actor=owner, document_id=doc.id, sensitivity="nonsense")

    _migrate()
    asyncio.run(run())


def test_no_leak_after_blocked_org_wide_restricted_share(tmp_path):
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, _, budi = await _users(session)
            storage = LocalObjectStorage(tmp_path / "objects")
            doc = await _seed_doc(session, storage, owner)
            await update_sensitivity(session, actor=owner, document_id=doc.id, sensitivity="restricted")

            with pytest.raises(AppError):
                await share_document(session, RecordingAuthz(), actor=owner, document_id=doc.id,
                                     principal=f"org:{budi.org_id}")

            # Budi (in the same org) still sees nothing: no rows, no title/content/existence hint.
            assert await visible_chunks(session, await principals(session, budi)) == []
            answer = await answer_question(session, embedder=FakeEmbedder(), user=budi, question=QUESTION)
            assert answer["citations"] == []
            assert "WhatsApp" not in answer["answer"]
            assert "30 percent" not in answer["answer"]

    _migrate()
    asyncio.run(run())


def test_sensitivities_tuple_is_the_four_labels():
    assert SENSITIVITIES == ("public", "internal", "confidential", "restricted")
