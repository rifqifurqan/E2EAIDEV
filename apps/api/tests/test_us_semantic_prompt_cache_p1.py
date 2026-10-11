"""Semantic/prompt caching keyed on permission set (FR-M4).

Cache keys and metadata must never contain raw prompts, answers, document text, secrets, tokens,
or principal identifiers. The permission set hash is the isolation boundary: same question/model but a
different principal set is a miss.
"""

import asyncio
import subprocess

from sqlalchemy import delete, func, select

from e2eai.db import Chunk, ChunkEmbedding, Conversation, DocPrincipal, Document, DocumentVersion, Folder, User, sessions
from e2eai.documents import create_seeded_document, share_document
from e2eai.retrieval import answer_question, index_document_chunks
from e2eai.seed import seed_demo
from e2eai.semantic_cache import (
    CacheContext,
    SemanticPromptCache,
    build_prompt_cache_key,
    permission_set_hash,
)


def test_permission_set_hash_is_order_stable_and_isolates_principals() -> None:
    a = permission_set_hash(["team:sales", "user:andi", "role:business_user"])
    b = permission_set_hash(["role:business_user", "user:andi", "team:sales"])
    c = permission_set_hash(["team:hr", "user:budi", "role:business_user"])

    assert a == b
    assert a != c
    assert "andi" not in a and "sales" not in a and "user:" not in a


def test_prompt_cache_key_contains_safe_dimensions_not_raw_prompt_or_principals() -> None:
    ctx = CacheContext(
        principals=["user:andi", "team:sales"],
        bot_version="bot-v1",
        index_version="idx-v3",
        prompt_version="prompt-v2",
        model="qwen-small",
        retrieval_mode="hybrid",
        scope="shared_with_me",
    )

    key = build_prompt_cache_key("What is the WhatsApp partnership revenue share?", ctx)

    assert key.startswith("fr-m4:")
    for forbidden in (
        "WhatsApp", "partnership", "revenue", "share",
        "andi", "sales", "user:", "team:", "secret", "token", "password",
    ):
        assert forbidden.lower() not in key.lower()
    assert build_prompt_cache_key("What is the WhatsApp partnership revenue share?", ctx) == key


def test_semantic_prompt_cache_never_reuses_across_permission_sets() -> None:
    cache = SemanticPromptCache()
    sales_ctx = CacheContext(
        principals=["user:andi", "team:sales"],
        bot_version="bot-v1",
        index_version="idx-v1",
        prompt_version="prompt-v1",
        model="qwen-small",
    )
    hr_ctx = CacheContext(
        principals=["user:budi", "team:hr"],
        bot_version="bot-v1",
        index_version="idx-v1",
        prompt_version="prompt-v1",
        model="qwen-small",
    )

    cache.put(
        "What is the WhatsApp partnership revenue share?",
        sales_ctx,
        {"answer": "30 percent", "citations": [{"document": "WhatsApp Partnership"}]},
    )

    assert cache.get("What is the WhatsApp partnership revenue share?", sales_ctx)["answer"] == "30 percent"
    assert cache.get("What is the WhatsApp partnership revenue share?", hr_ctx) is None

    metadata = cache.safe_metadata("What is the WhatsApp partnership revenue share?", sales_ctx)
    serialized = repr(metadata).lower()
    for forbidden in ("whatsapp", "partnership", "revenue", "share", "andi", "sales", "30 percent"):
        assert forbidden not in serialized


# ---------------------------------------------------------------------------
# Answer-path cache boundary
# ---------------------------------------------------------------------------
class RecordingAuthz:
    async def write(self, writes=(), deletes=()):
        return None


class RecordingEmbedder:
    model = "fake-embedding-v1"
    _axes = ("revenue", "holiday")

    def __init__(self):
        self.calls: list[str] = []

    async def embed(self, texts):
        self.calls.extend(texts)
        return [[float(t.lower().count(a)) for a in self._axes] for t in texts]


class ExplodingEmbedder:
    model = "fake-embedding-v1"

    async def embed(self, texts):  # pragma: no cover - should never be called on a cache hit
        raise AssertionError("cache hit should not embed or retrieve again")


async def _reset(session):
    for model in (Conversation, ChunkEmbedding, DocPrincipal, Chunk, DocumentVersion, Document, Folder):
        await session.execute(delete(model))
    await session.commit()


def test_answer_question_uses_permission_scoped_cache_without_cross_user_reuse():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)

    async def run():
        async with sessions()() as session:
            await _reset(session)
            await seed_demo(session, password="TestPassword_123456789")
            owner = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))
            andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
            budi = await session.scalar(select(User).where(func.lower(User.email) == "budi@demo.e2eai"))
            doc = await create_seeded_document(
                session, owner=owner, title="WhatsApp Partnership",
                text="The WhatsApp partnership revenue share is 30 percent.", page=4)
            await share_document(session, RecordingAuthz(), actor=owner,
                                 document_id=doc.id, principal=f"user:{andi.id}")
            await index_document_chunks(session, embedder=RecordingEmbedder(), document_id=doc.id)

            cache = SemanticPromptCache()
            first = await answer_question(
                session, embedder=RecordingEmbedder(), user=andi,
                question="What is the revenue share?", semantic_cache=cache,
            )
            assert first["cache"]["hit"] is False
            assert "30 percent" in first["answer"]

            second = await answer_question(
                session, embedder=ExplodingEmbedder(), user=andi,
                question="What is the revenue share?", semantic_cache=cache,
            )
            assert second["cache"]["hit"] is True
            assert second["answer"] == first["answer"]

            budi_result = await answer_question(
                session, embedder=RecordingEmbedder(), user=budi,
                question="What is the revenue share?", semantic_cache=cache,
            )
            assert budi_result["cache"]["hit"] is False
            assert budi_result["citations"] == []
            assert "30 percent" not in budi_result["answer"]

    asyncio.run(run())
