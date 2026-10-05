"""PII discovery/redaction guardrail for ingest/traces (FR-D6, FR-O12, FR-O9, FR-C8).

Tests are offline and deterministic: local regex detector covers the Indonesian-lite MVP while the
Presidio adapter stays behind a boundary for later deployments. Audit details must never contain raw PII.
"""

import asyncio
import json
import subprocess

from sqlalchemy import delete, func, select

from e2eai.db import AuditEntry, Chunk, ChunkEmbedding, DocPrincipal, Document, DocumentVersion, Folder, User, sessions
from e2eai.documents import LocalObjectStorage, create_uploaded_document, share_document
from e2eai.ingest import ingest_version
from e2eai.pii import PiiPolicy, PresidioPiiDetector, RegexPiiDetector, mask_text
from e2eai.retrieval import answer_question
from e2eai.seed import seed_demo

PII_TEXT = (
    "# HR Contact\n\n"
    "Email andi@example.com, phone +62 812-3456-7890, "
    "NIK 3173050101010001, rekening 123456789012. Revenue share stays 30 percent."
).encode()
QUESTION = "What is the HR contact revenue share?"


class RecordingAuthz:
    async def write(self, writes=(), deletes=()):
        return None


class FakeEmbedder:
    model = "fake-embedding-v1"

    async def embed(self, texts):
        return [[1.0, float("30 percent" in text or "revenue" in text.lower())] for text in texts]


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


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


def test_regex_detector_finds_mvp_pii_and_mask_text_replaces_values():
    text = PII_TEXT.decode()
    findings = RegexPiiDetector().detect(text)
    types = {f.type for f in findings}
    assert {"email", "phone", "nik", "account_number"}.issubset(types)

    masked = mask_text(text, findings)
    assert "andi@example.com" not in masked
    assert "+62 812-3456-7890" not in masked
    assert "3173050101010001" not in masked
    assert "123456789012" not in masked
    assert "[EMAIL]" in masked
    assert "[PHONE]" in masked
    assert "[NIK]" in masked
    assert "[ACCOUNT_NUMBER]" in masked


def test_presidio_adapter_boundary_is_clear_when_dependency_absent():
    try:
        import presidio_analyzer  # noqa: F401
    except ImportError:
        import pytest
        from e2eai.core.errors import AppError

        with pytest.raises(AppError) as ei:
            PresidioPiiDetector().detect("andi@example.com")
        assert ei.value.status == 503


def test_ingest_detect_only_preserves_chunk_text_but_audit_has_no_raw_pii(tmp_path):
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, _andi, _budi = await _users(session)
            storage = LocalObjectStorage(tmp_path / "objects")
            doc = await create_uploaded_document(
                session, owner=owner, title="hr.md", data=PII_TEXT, mime="text/markdown", storage=storage
            )
            result = await ingest_version(
                session,
                embedder=FakeEmbedder(),
                version_id=doc.current_version_id,
                storage=storage,
                pii_policy=PiiPolicy(detect=True, redact_document_text=False, mask_traces=True),
            )
            assert result["status"] == "ready"
            assert result["pii_findings"] >= 4
            chunk_text = await session.scalar(select(Chunk.text))
            assert "andi@example.com" in chunk_text
            pii_audit = await session.scalar(
                select(AuditEntry).where(AuditEntry.action == "document.pii.detected", AuditEntry.target == f"document:{doc.id}")
            )
            encoded = json.dumps(pii_audit.details, sort_keys=True)
            assert "andi@example.com" not in encoded
            assert "+62" not in encoded
            assert "3173050101010001" not in encoded
            assert pii_audit.details["counts"]["email"] == 1
            assert pii_audit.details["redacted"] is False

    _migrate()
    asyncio.run(run())


def test_ingest_redaction_masks_chunks_cited_answer_and_unshared_user_gets_no_leak(tmp_path):
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi, budi = await _users(session)
            storage = LocalObjectStorage(tmp_path / "objects")
            doc = await create_uploaded_document(
                session, owner=owner, title="hr.md", data=PII_TEXT, mime="text/markdown", storage=storage
            )
            result = await ingest_version(
                session,
                embedder=FakeEmbedder(),
                version_id=doc.current_version_id,
                storage=storage,
                pii_policy=PiiPolicy(detect=True, redact_document_text=True, mask_traces=True),
            )
            assert result["status"] == "ready"
            chunk_text = await session.scalar(select(Chunk.text))
            assert "andi@example.com" not in chunk_text
            assert "3173050101010001" not in chunk_text
            assert "[EMAIL]" in chunk_text
            assert "[NIK]" in chunk_text

            await share_document(session, RecordingAuthz(), actor=owner, document_id=doc.id, principal=f"user:{andi.id}")
            andi_answer = await answer_question(session, embedder=FakeEmbedder(), user=andi, question=QUESTION)
            assert "[EMAIL]" in andi_answer["answer"]
            assert "andi@example.com" not in andi_answer["answer"]
            assert andi_answer["citations"]

            budi_answer = await answer_question(session, embedder=FakeEmbedder(), user=budi, question=QUESTION)
            assert budi_answer["citations"] == []
            assert "[EMAIL]" not in budi_answer["answer"]
            assert "andi@example.com" not in budi_answer["answer"]
            assert "30 percent" not in budi_answer["answer"]

    _migrate()
    asyncio.run(run())
