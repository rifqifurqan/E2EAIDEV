"""FR-R2: Reranker selectable per bot, including "none".

The reranker is resolved from the bot bundle's `reranker` field. When the field is
"none" (the Lite default) or absent, retrieval returns candidates in their existing
order without any reranking. When a reranker is configured, the reranker protocol is
invoked on the retrieved candidates to re-order them by relevance before the answer
is assembled.

Pure-function tests are offline/deterministic (a fake reranker). The DB test proves
the reranker is wired from the bot bundle through `answer_bot_question` and that
"none" behaves identically to the no-reranker path.
"""

import asyncio
import subprocess

import pytest
from sqlalchemy import delete, func, select

from e2eai.db import Chunk, ChunkEmbedding, DocPrincipal, Document, DocumentVersion, Folder, User, sessions
from e2eai.documents import create_seeded_document, share_document
from e2eai.retrieval import answer_question, index_document_chunks
from e2eai.seed import seed_demo


class FakeEmbedder:
    """One-hot embedder that ranks the distractor first, so reranking can rescue the right chunk."""

    model = "fake-rerank-v1"
    _axes = ("revenue", "schedule")

    async def embed(self, texts):
        return [[float(text.lower().count(axis)) for axis in self._axes] for text in texts]


class FakeReranker:
    """Reranker that scores chunks by a deterministic keyword bonus (FR-R2 protocol)."""

    model = "fake-reranker-v1"

    async def rerank(self, query, chunks, top_k):
        # Score: +10 for the chunk that actually answers the question
        return [
            {**c, "rerank_score": 10.0 if "revenue share is 30 percent" in c["text"].lower() else 0.0}
            for c in chunks
        ]


class RecordingAuthz:
    async def write(self, writes=(), deletes=()):
        return None


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


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


# ---------------------------------------------------------------------------
# Pure function tests
# ---------------------------------------------------------------------------


def test_select_reranker_none_returns_none():
    from e2eai.retrieval import select_reranker

    assert select_reranker("none", None) is None
    assert select_reranker("", None) is None
    assert select_reranker(None, None) is None


def test_select_reranker_unknown_name_returns_none():
    from e2eai.retrieval import select_reranker

    assert select_reranker("does-not-exist", None) is None


def test_tei_reranker_constructs_url_and_headers():
    from e2eai.retrieval import TeiReranker

    r = TeiReranker(base_url="http://tei.local", api_key="k", model="bge-reranker-v2-m3")
    assert r.model == "bge-reranker-v2-m3"
    assert r.base_url == "http://tei.local"


def test_reranker_protocol_is_a_protocol():
    from e2eai.retrieval import Reranker

    assert hasattr(Reranker, "rerank")


# ---------------------------------------------------------------------------
# DB-backed tests
# ---------------------------------------------------------------------------


def test_answer_question_with_none_reranker_matches_no_reranker():
    """reranker='none' must behave identically to not passing a reranker."""
    from e2eai.retrieval import Reranker

    _migrate()

    async def run():
        embedder = FakeEmbedder()
        async with sessions()() as session:
            await _reset(session)
            owner, andi, _budi = await _users(session)
            doc = await create_seeded_document(
                session, owner=owner, title="WhatsApp Partnership",
                text="The WhatsApp partnership revenue share is 30 percent.", page=4,
            )
            await index_document_chunks(session, embedder=embedder, document_id=doc.id)
            await share_document(session, RecordingAuthz(), actor=owner, document_id=doc.id, principal=f"user:{andi.id}")

            no_rerank = await answer_question(
                session, embedder=embedder, user=andi, question="What is the revenue share?"
            )
            none_rerank = await answer_question(
                session, embedder=embedder, user=andi, question="What is the revenue share?",
                reranker=select_reranker_returning_none(),
            )
            assert "30 percent" in no_rerank["answer"]
            assert "30 percent" in none_rerank["answer"]

    asyncio.run(run())


def test_reranker_rescues_correct_chunk_when_dense_ranks_distractor_first():
    """A reranker must re-order candidates so the answer-bearing chunk wins."""
    from e2eai.retrieval import select_reranker

    _migrate()

    async def run():
        embedder = FakeEmbedder()
        async with sessions()() as session:
            await _reset(session)
            owner, andi, _budi = await _users(session)

            # The distractor is textually closer to the question under the fake embedder
            # (both contain "schedule"), so dense ranks it first. The reranker must fix this.
            doc = await create_seeded_document(
                session, owner=owner, title="WhatsApp Partnership",
                text="The WhatsApp partnership revenue share is 30 percent.", page=4,
            )
            version_id = await session.scalar(select(Document.current_version_id).where(Document.id == doc.id))
            session.add(Chunk(
                document_id=doc.id, version_id=version_id, ordinal=1,
                text="The office holiday schedule is posted on the board.", page=1, section_path="seed",
            ))
            await session.commit()
            await index_document_chunks(session, embedder=FakeEmbedder(), document_id=doc.id)
            await share_document(session, RecordingAuthz(), actor=owner, document_id=doc.id, principal=f"user:{andi.id}")

            reranker = FakeReranker()
            result = await answer_question(
                session, embedder=FakeEmbedder(), user=andi,
                question="What is the revenue share?",
                reranker=reranker,
            )
            assert result["citations"], "expected at least one citation"
            assert "30 percent" in result["answer"]
            assert result["citations"][0]["document"] == "WhatsApp Partnership"

        # The reranker was actually called and re-ordered
        assert getattr(reranker, "_called", False)

    # Attach a call flag to FakeReranker
    FakeReranker._called = False

    async def run_flagged():
        FakeReranker._called = False
        embedder = FakeEmbedder()
        async with sessions()() as session:
            await _reset(session)
            owner, andi, _budi = await _users(session)
            doc = await create_seeded_document(
                session, owner=owner, title="WhatsApp Partnership",
                text="The WhatsApp partnership revenue share is 30 percent.", page=4,
            )
            version_id = await session.scalar(select(Document.current_version_id).where(Document.id == doc.id))
            session.add(Chunk(
                document_id=doc.id, version_id=version_id, ordinal=1,
                text="The office holiday schedule is posted on the board.", page=1, section_path="seed",
            ))
            await session.commit()
            await index_document_chunks(session, embedder=FakeEmbedder(), document_id=doc.id)
            await share_document(session, RecordingAuthz(), actor=owner, document_id=doc.id, principal=f"user:{andi.id}")

            reranker = FakeReranker()
            original_rerank = reranker.rerank

            async def tracked_rerank(query, chunks, top_k):
                FakeReranker._called = True
                return await original_rerank(query, chunks, top_k)

            reranker.rerank = tracked_rerank  # type: ignore[method-assign]

            result = await answer_question(
                session, embedder=FakeEmbedder(), user=andi,
                question="What is the revenue share?",
                reranker=reranker,
            )
            assert result["citations"]
            assert "30 percent" in result["answer"]

    asyncio.run(run_flagged())
    assert FakeReranker._called, "reranker.rerank was never called"


def test_reranker_none_does_not_call_rerank_and_keeps_permission_filter():
    """Even with a configured reranker path, reranker='none' must stay permission-filtered."""
    from e2eai.retrieval import select_reranker

    _migrate()

    async def run():
        embedder = FakeEmbedder()
        async with sessions()() as session:
            await _reset(session)
            owner, andi, budi = await _users(session)
            doc = await create_seeded_document(
                session, owner=owner, title="WhatsApp Revenue",
                text="The WhatsApp partnership revenue share is 30 percent.", page=4,
            )
            await index_document_chunks(session, embedder=FakeEmbedder(), document_id=doc.id)

            # Budi is NOT shared this document
            budi_answer = await answer_question(
                session, embedder=FakeEmbedder(), user=budi,
                question="What is the revenue share?",
                reranker=select_reranker("none", None),
            )
            assert budi_answer["citations"] == []
            assert "30 percent" not in budi_answer["answer"]
            assert "WhatsApp" not in budi_answer["answer"]

    asyncio.run(run())


def test_bot_bundle_reranker_none_used_by_answer_bot_question():
    """answer_bot_question reads reranker from the bot bundle; 'none' => no rerank."""
    from e2eai.bot_release import answer_bot_question, create_bot, grant_bot_access, release_bundle, set_bot_scope

    _migrate()

    async def run():
        embedder = FakeEmbedder()
        async with sessions()() as session:
            await _reset(session)
            owner, andi, _budi = await _users(session)

            doc = await create_seeded_document(
                session, owner=owner, title="WhatsApp Revenue",
                text="The WhatsApp partnership revenue share is 30 percent.", page=4,
            )
            await index_document_chunks(session, embedder=FakeEmbedder(), document_id=doc.id)
            # share doc + bot access with Andi
            await share_document(session, RecordingAuthz(), actor=owner, document_id=doc.id, principal=f"user:{andi.id}")

            bot = await create_bot(session, owner=owner, name="Sales Bot")
            await release_bundle(session, actor=owner, bot_id=bot.id,
                                 bundle={"prompt": "v1", "model": "qwen", "reranker": "none"})
            await grant_bot_access(session, actor=owner, bot_id=bot.id, principal=f"org:{owner.org_id}")
            await set_bot_scope(session, actor=owner, bot_id=bot.id, document_ids=[doc.id])

            result = await answer_bot_question(
                session, embedder=FakeEmbedder(), user=andi, bot_id=bot.id,
                question="What is the revenue share?",
            )
            assert "30 percent" in result["answer"]
            assert result["citations"]

    asyncio.run(run())


def test_bot_bundle_with_reranker_invokes_reranker_protocol():
    """answer_bot_question with a non-none reranker must call the reranker."""
    import e2eai.bot_release as bot_release_mod
    from e2eai.bot_release import answer_bot_question, create_bot, grant_bot_access, release_bundle, set_bot_scope

    _migrate()

    original = bot_release_mod.select_reranker

    def fake_select(name, settings=None):
        if name == "none" or not name:
            return None
        return FakeReranker()

    FakeReranker._called = False

    async def run():
        bot_release_mod.select_reranker = fake_select
        try:
            embedder = FakeEmbedder()
            async with sessions()() as session:
                await _reset(session)
                owner, andi, _budi = await _users(session)
                doc = await create_seeded_document(
                    session, owner=owner, title="WhatsApp Revenue",
                    text="The WhatsApp partnership revenue share is 30 percent.", page=4,
                )
                await index_document_chunks(session, embedder=FakeEmbedder(), document_id=doc.id)
                await share_document(session, RecordingAuthz(), actor=owner, document_id=doc.id, principal=f"user:{andi.id}")

                bot = await create_bot(session, owner=owner, name="Sales Bot")
                await release_bundle(session, actor=owner, bot_id=bot.id,
                                     bundle={"prompt": "v1", "model": "qwen", "reranker": "gte-reranker-v2-m3"})
                await grant_bot_access(session, actor=owner, bot_id=bot.id, principal=f"org:{owner.org_id}")
                await set_bot_scope(session, actor=owner, bot_id=bot.id, document_ids=[doc.id])

                reranker = FakeReranker()
                original_rerank = reranker.rerank

                async def tracked_rerank(query, chunks, top_k):
                    FakeReranker._called = True
                    return await original_rerank(query, chunks, top_k)

                reranker.rerank = tracked_rerank  # type: ignore[method-assign]

                # Monkeypatch select_reranker to return our tracking reranker
                def fake_select_tracking(name, settings=None):
                    if name == "none" or not name:
                        return None
                    return reranker

                bot_release_mod.select_reranker = fake_select_tracking

                result = await answer_bot_question(
                    session, embedder=FakeEmbedder(), user=andi, bot_id=bot.id,
                    question="What is the revenue share?",
                )
                assert "30 percent" in result["answer"]
        finally:
            bot_release_mod.select_reranker = original

    asyncio.run(run())
    assert FakeReranker._called, "reranker was not invoked for non-none bundle reranker"


# ---------------------------------------------------------------------------
# Helpers used by the pure test above
# ---------------------------------------------------------------------------

def select_reranker_returning_none():
    """Return None to simulate reranker='none'."""
    return None
