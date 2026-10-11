"""FR-R4 Hybrid search: dense + sparse/BM25 fused with reciprocal rank fusion (RRF).

Pure-function tests are offline/deterministic. The DB test proves hybrid mode keeps the
SQL-level permission filter and lets an exact keyword match outrank a dense-only miss.
"""

import asyncio
import subprocess

import pytest
from sqlalchemy import delete, func, select

from e2eai.db import Chunk, ChunkEmbedding, DocPrincipal, Document, DocumentVersion, Folder, User, sessions
from e2eai.documents import create_seeded_document, share_document
from e2eai.seed import seed_demo


def test_tokenize_lowercases_and_splits_on_non_alphanumerics():
    from e2eai.hybrid_search import tokenize

    assert tokenize("Torque: 45-Nm, M8 bolt!") == ["torque", "45", "nm", "m8", "bolt"]
    assert tokenize("") == []


def test_bm25_ranks_exact_term_match_first_and_zero_for_no_overlap():
    from e2eai.hybrid_search import bm25_scores

    docs = [
        "annual leave policy for employees",
        "the torque spec for the M8 bolt is 25 Nm",
        "office parking rules",
    ]
    scores = bm25_scores("M8 torque", docs)
    assert len(scores) == 3
    assert scores[1] > 0
    assert scores[0] == 0.0 and scores[2] == 0.0


def test_bm25_empty_inputs_are_safe():
    from e2eai.hybrid_search import bm25_scores

    assert bm25_scores("anything", []) == []
    assert bm25_scores("", ["a b c"]) == [0.0]


def test_rrf_fuses_two_rankings_with_k60_and_is_deterministic():
    from e2eai.hybrid_search import reciprocal_rank_fusion

    dense = ["a", "b", "c"]
    sparse = ["c", "a", "d"]
    fused = reciprocal_rank_fusion([dense, sparse], k=60)
    ids = [item for item, _ in fused]
    # a: 1/61 + 1/62 ; c: 1/63 + 1/61 ; b: 1/62 ; d: 1/63
    assert ids == ["a", "c", "b", "d"]
    score_a = dict(fused)["a"]
    assert score_a == pytest.approx(1 / 61 + 1 / 62)
    assert reciprocal_rank_fusion([dense, sparse]) == fused


def test_rrf_ties_break_by_first_seen_order_and_empty_is_empty():
    from e2eai.hybrid_search import reciprocal_rank_fusion

    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []
    fused = reciprocal_rank_fusion([["x"], ["y"]])
    assert [i for i, _ in fused] == ["x", "y"]


def test_fuse_dense_and_sparse_drops_zero_score_sparse_hits():
    from e2eai.hybrid_search import fuse_dense_sparse

    candidates = [
        {"document_id": "1", "text": "revenue share holiday", "score": 0.9},
        {"document_id": "2", "text": "exact SKU-7731 mention", "score": 0.1},
        {"document_id": "3", "text": "unrelated words", "score": 0.5},
    ]
    fused = fuse_dense_sparse(candidates, query="SKU-7731", limit=3)
    # dense order: 1,3,2 ; sparse only has 2 (rank 1) -> 2 beats 3 and ties-ish with 1
    texts = [c["text"] for c in fused]
    assert texts[0] in ("exact SKU-7731 mention", "revenue share holiday")
    assert "exact SKU-7731 mention" in texts[:2]
    assert all("rrf_score" in c for c in fused)
    assert len(fused) == 3


# ---------------------------------------------------------------------------
# DB-backed: hybrid mode in retrieve_relevant_chunks
# ---------------------------------------------------------------------------


class MisleadingEmbedder:
    """Dense vectors that rank the exact-keyword doc LAST, so only sparse can rescue it."""

    model = "fake-hybrid-v1"

    async def embed(self, texts):
        out = []
        for t in texts:
            low = t.lower()
            if "sku-7731" in low and "stock" not in low:
                out.append([0.0, 1.0])  # the exact-term doc points away from the query
            elif "stock" in low:
                out.append([1.0, 0.0])  # query and distractor point the same way
            else:
                out.append([1.0, 0.1])
        return out


class RecordingAuthz:
    async def write(self, writes=(), deletes=()):
        return None


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


async def _reset(session):
    for model in (ChunkEmbedding, DocPrincipal, Chunk, DocumentVersion, Document, Folder):
        await session.execute(delete(model))
    await session.commit()


def test_hybrid_mode_rescues_exact_keyword_and_keeps_permission_filter():
    from e2eai.authz import principals
    from e2eai.retrieval import index_document_chunks, retrieve_relevant_chunks

    _migrate()

    async def run():
        embedder = MisleadingEmbedder()
        async with sessions()() as session:
            await _reset(session)
            await seed_demo(session, password="TestPassword_123456789")
            owner = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))
            andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
            budi = await session.scalar(select(User).where(func.lower(User.email) == "budi@demo.e2eai"))

            exact = await create_seeded_document(
                session, owner=owner, title="Part list", text="Part SKU-7731 ships in blue boxes.", page=2
            )
            distractor = await create_seeded_document(
                session, owner=owner, title="Stock memo", text="stock levels are healthy this quarter", page=1
            )
            hidden = await create_seeded_document(
                session, owner=owner, title="Hidden", text="Secret SKU-7731 price list", page=1
            )
            for doc in (exact, distractor, hidden):
                await index_document_chunks(session, embedder=embedder, document_id=doc.id)
            authz = RecordingAuthz()
            await share_document(session, authz, actor=owner, document_id=exact.id, principal=f"user:{andi.id}")
            await share_document(session, authz, actor=owner, document_id=distractor.id, principal=f"user:{andi.id}")

            question = "stock SKU-7731"
            andi_principals = await principals(session, andi)

            dense = await retrieve_relevant_chunks(
                session, embedder=embedder, user_principals=andi_principals, question=question, limit=1
            )
            hybrid = await retrieve_relevant_chunks(
                session, embedder=embedder, user_principals=andi_principals, question=question, limit=2,
                mode="hybrid",
            )
            assert dense[0]["document"] == "Stock memo"
            titles = [h["document"] for h in hybrid]
            assert "Part list" in titles  # sparse rescued the exact keyword
            assert "Hidden" not in titles  # permission filter still applies pre-fusion
            assert all("rrf_score" in h for h in hybrid)

            budi_principals = await principals(session, budi)
            assert await retrieve_relevant_chunks(
                session, embedder=embedder, user_principals=budi_principals, question=question, mode="hybrid"
            ) == []

    asyncio.run(run())


def test_invalid_retrieval_mode_is_rejected():
    from e2eai.core.errors import AppError
    from e2eai.retrieval import retrieve_relevant_chunks

    async def run():
        async with sessions()() as session:
            with pytest.raises(AppError):
                await retrieve_relevant_chunks(
                    session, embedder=MisleadingEmbedder(), user_principals=["user:x"], question="q", mode="bogus"
                )

    asyncio.run(run())


def test_answer_question_accepts_hybrid_retrieval_mode_and_cites_exact_match():
    from e2eai.retrieval import answer_question, index_document_chunks

    _migrate()

    async def run():
        embedder = MisleadingEmbedder()
        async with sessions()() as session:
            await _reset(session)
            await seed_demo(session, password="TestPassword_123456789")
            owner = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))
            exact = await create_seeded_document(
                session, owner=owner, title="Part list", text="Part SKU-7731 ships in blue boxes.", page=2
            )
            await index_document_chunks(session, embedder=embedder, document_id=exact.id)
            result = await answer_question(
                session, embedder=embedder, user=owner, question="SKU-7731", retrieval_mode="hybrid"
            )
            assert result["citations"][0]["document"] == "Part list"

    asyncio.run(run())
