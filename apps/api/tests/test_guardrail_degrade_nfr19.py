"""NFR-19: an unavailable guardrail degrades its feature unless it is mandatory, in which case it blocks."""

import asyncio
import subprocess

import pytest
from sqlalchemy import delete, func, select

from e2eai.core.errors import AppError
from e2eai.db import AuditEntry, Chunk, ChunkEmbedding, DocPrincipal, Document, DocumentVersion, Folder, User, sessions
from e2eai.documents import create_seeded_document, share_document
from e2eai.guardrails import PromptGuardPolicy
from e2eai.retrieval import answer_question, index_document_chunks
from e2eai.seed import seed_demo

QUESTION = "What is the revenue share?"
BENIGN = "The WhatsApp revenue share is 30 percent."


class RecordingAuthz:
    async def write(self, writes=(), deletes=()):
        return None

    async def check(self, *a, **k):
        return True


class FakeEmbedder:
    model = "fake-embedding-v1"

    async def embed(self, texts):
        return [[0.9, 0.1] for _ in texts]


class DownDetector:
    def detect(self, text):
        raise AppError(503, "Prompt guard detector unavailable", "down")


def test_policy_is_mandatory_by_default():
    assert PromptGuardPolicy().mandatory is True


async def _setup(session):
    for model in (ChunkEmbedding, DocPrincipal, Chunk, DocumentVersion, Document, Folder):
        await session.execute(delete(model))
    await session.commit()
    await seed_demo(session, password="TestPassword_123456789")
    owner = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))
    andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
    doc = await create_seeded_document(session, owner=owner, title="Deal", text=BENIGN, page=1)
    await share_document(session, RecordingAuthz(), actor=owner, document_id=doc.id, principal=f"user:{andi.id}")
    await index_document_chunks(session, embedder=FakeEmbedder(), document_id=doc.id)
    return andi


def test_optional_guardrail_outage_degrades_and_is_audited_and_reported():
    async def run():
        async with sessions()() as session:
            andi = await _setup(session)
            await session.execute(delete(AuditEntry).where(AuditEntry.action == "retrieval.guardrail.degraded"))
            await session.commit()
            result = await answer_question(
                session, embedder=FakeEmbedder(), user=andi, question=QUESTION,
                prompt_detector=DownDetector(), prompt_policy=PromptGuardPolicy(mandatory=False),
                include_explainability=True,
            )
            assert "30 percent" in result["answer"]  # chat stays up
            status = result["explainability"]["guardrail_status"]
            assert status["degraded"] is True and status["prompt_guard_enabled"] is False
            rows = (await session.scalars(select(AuditEntry).where(AuditEntry.action == "retrieval.guardrail.degraded"))).all()
            assert len(rows) == 1 and rows[0].details == {"guardrail": "prompt_guard", "reason": "detector_unavailable"}

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
    asyncio.run(run())


def test_mandatory_guardrail_outage_blocks_with_clear_503():
    async def run():
        async with sessions()() as session:
            andi = await _setup(session)
            with pytest.raises(AppError) as exc:
                await answer_question(
                    session, embedder=FakeEmbedder(), user=andi, question=QUESTION,
                    prompt_detector=DownDetector(), prompt_policy=PromptGuardPolicy(mandatory=True),
                )
            assert exc.value.status == 503

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
    asyncio.run(run())


def test_unexpected_detector_exception_is_treated_as_outage_not_500():
    class Boom:
        def detect(self, text):
            raise RuntimeError("model crashed at /internal/path token=abc")

    async def run():
        async with sessions()() as session:
            andi = await _setup(session)
            with pytest.raises(AppError) as exc:
                await answer_question(
                    session, embedder=FakeEmbedder(), user=andi, question=QUESTION,
                    prompt_detector=Boom(), prompt_policy=PromptGuardPolicy(mandatory=True),
                )
            assert exc.value.status == 503 and "internal" not in str(exc.value.detail if hasattr(exc.value, "detail") else exc.value)

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
    asyncio.run(run())
