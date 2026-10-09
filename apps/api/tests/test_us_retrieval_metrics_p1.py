"""FR-R8 Retrieval metrics: recall@k, MRR, nDCG@k with per-slice aggregation.

Tests verify:
1. Pure metric math (recall@k, MRR, nDCG@k) with known inputs.
2. Per-slice aggregation across language slices (id, en, id_question_en_source, en_question_id_source).
3. Runner uses permission-filtered retrieval path — unshared docs never counted.
4. API returns safe metrics only, no restricted text.
5. Results stored as EvalRun consistent with existing Eval Lab.
"""

import asyncio
import subprocess
import uuid

from sqlalchemy import delete, func, select

from e2eai.db import (
    Chunk,
    ChunkEmbedding,
    DocPrincipal,
    Document,
    DocumentVersion,
    EvalDataset,
    EvalRun,
    Folder,
    User,
    sessions,
)
from e2eai.documents import create_seeded_document, share_document
from e2eai.retrieval import index_document_chunks
from e2eai.retrieval_metrics import (
    RetrievalMetricsAdapter,
    compute_mrr,
    compute_ndcg_at_k,
    compute_recall_at_k,
    run_retrieval_metrics,
)
from e2eai.eval_lab import create_dataset
from e2eai.seed import seed_demo


class RecordingAuthz:
    async def write(self, writes=(), deletes=()):
        return None


class FakeEmbedder:
    """Deterministic keyword one-hot embedder: ranks 'revenue' chunks closest to revenue questions."""

    model = "fake-embedding-v1"
    _axes = ("revenue", "holiday", "policy")

    async def embed(self, texts):
        return [[float(text.lower().count(axis)) for axis in self._axes] for text in texts]


async def _reset(session):
    for model in (EvalRun, EvalDataset, ChunkEmbedding, DocPrincipal, Chunk, DocumentVersion, Document, Folder):
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


# ---------------------------------------------------------------------------
# 1. Pure metric math
# ---------------------------------------------------------------------------


def test_recall_at_k_exact_math():
    """recall@k = |relevant ∩ retrieved[:k]| / |relevant|."""
    # 2 of 3 relevant in top-5
    assert compute_recall_at_k(["a", "x", "b", "y", "z"], {"a", "b", "c"}, k=5) == round(2 / 3, 4)
    # All relevant in top-3
    assert compute_recall_at_k(["a", "b", "c", "d"], {"a", "b", "c"}, k=3) == 1.0
    # None relevant
    assert compute_recall_at_k(["x", "y", "z"], {"a", "b"}, k=3) == 0.0
    # Empty relevant set -> 0.0 (avoid division by zero)
    assert compute_recall_at_k(["a", "b"], set(), k=2) == 0.0
    # k larger than retrieved
    assert compute_recall_at_k(["a"], {"a", "b"}, k=10) == 0.5


def test_mrr_exact_math():
    """MRR = 1/rank of first relevant document."""
    assert compute_mrr(["x", "a", "y"], {"a", "b"}) == 0.5  # rank 2
    assert compute_mrr(["a", "x", "y"], {"a"}) == 1.0  # rank 1
    assert compute_mrr(["x", "y", "z"], {"a"}) == 0.0  # not found
    assert compute_mrr([], {"a"}) == 0.0


def test_ndcg_at_k_exact_math():
    """nDCG@k with binary relevance."""
    # Perfect ranking: relevant doc at position 1
    assert compute_ndcg_at_k(["a", "x"], {"a"}, k=2) == 1.0
    # Relevant at position 2 only
    ndcg = compute_ndcg_at_k(["x", "a"], {"a"}, k=2)
    # ideal DCG = 1/log2(2) = 1.0; actual DCG = 1/log2(3) ≈ 0.6309
    assert 0.63 <= ndcg <= 0.64
    # No relevant -> 0
    assert compute_ndcg_at_k(["x", "y"], {"a"}, k=2) == 0.0
    # Empty relevant set -> 0
    assert compute_ndcg_at_k(["a", "b"], set(), k=2) == 0.0


# ---------------------------------------------------------------------------
# 2. Per-slice aggregation with cross-lingual labels
# ---------------------------------------------------------------------------


def test_per_slice_aggregation_groups_by_language_slice():
    """Aggregate metrics per language_slice label, including cross-lingual slices."""
    items = [
        {"question": "Apa pendapatan?", "relevant_document_ids": ["d1"], "language_slice": "id", "k": 3},
        {"question": "Berapa margin?", "relevant_document_ids": ["d1"], "language_slice": "id", "k": 3},
        {"question": "What is the revenue?", "relevant_document_ids": ["d1"], "language_slice": "en", "k": 3},
        {"question": "Apa revenue share?", "relevant_document_ids": ["d1"], "language_slice": "id_question_en_source", "k": 3},
        {"question": "What is kebijakan?", "relevant_document_ids": ["d2"], "language_slice": "en_question_id_source", "k": 3},
    ]
    # Simulate perfect retrieval results for each item
    per_item = [
        {"recall_at_k": 1.0, "mrr": 1.0, "ndcg_at_k": 1.0, "language_slice": "id"},
        {"recall_at_k": 0.0, "mrr": 0.0, "ndcg_at_k": 0.0, "language_slice": "id"},
        {"recall_at_k": 1.0, "mrr": 1.0, "ndcg_at_k": 1.0, "language_slice": "en"},
        {"recall_at_k": 1.0, "mrr": 0.5, "ndcg_at_k": 0.8, "language_slice": "id_question_en_source"},
        {"recall_at_k": 0.0, "mrr": 0.0, "ndcg_at_k": 0.0, "language_slice": "en_question_id_source"},
    ]

    from e2eai.retrieval_metrics import aggregate_by_slice
    slices = aggregate_by_slice(per_item)

    assert "id" in slices
    assert slices["id"]["count"] == 2
    assert slices["id"]["recall_at_k"] == 0.5  # (1.0 + 0.0) / 2
    assert "en" in slices
    assert slices["en"]["count"] == 1
    assert slices["en"]["recall_at_k"] == 1.0
    assert "id_question_en_source" in slices
    assert slices["id_question_en_source"]["mrr"] == 0.5
    assert "en_question_id_source" in slices
    assert slices["en_question_id_source"]["recall_at_k"] == 0.0


# ---------------------------------------------------------------------------
# 3. Runner with permission-filtered retrieval — no-leak
# ---------------------------------------------------------------------------


def test_runner_uses_permission_filtered_retrieval_and_stores_eval_run():
    """Runner retrieves through the existing permission path. Budi gets nothing, Andi gets metrics."""

    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi, budi = await _users(session)

            # Two docs: revenue (shared with Andi) and policy (owner only)
            rev_doc = await create_seeded_document(
                session, owner=owner, title="Revenue Report",
                text="The revenue share is 30 percent.", page=4,
            )
            pol_doc = await create_seeded_document(
                session, owner=owner, title="HR Policy",
                text="The holiday policy allows 12 days per year.", page=1,
            )
            await share_document(session, RecordingAuthz(), actor=owner,
                                 document_id=rev_doc.id, principal=f"user:{andi.id}")
            # pol_doc NOT shared with Andi or Budi
            for doc in (rev_doc, pol_doc):
                await index_document_chunks(session, embedder=FakeEmbedder(), document_id=doc.id)

            # Dataset: Andi asks about revenue; relevant doc is rev_doc
            ds = await create_dataset(
                session,
                name="retrieval-metrics-smoke",
                items=[
                    {
                        "question": "What is the revenue share?",
                        "relevant_document_ids": [str(rev_doc.id)],
                        "language_slice": "en",
                        "k": 5,
                    },
                ],
                source="manual",
                created_by=f"user:{owner.id}",
            )

            # Andi can see rev_doc -> recall@5 = 1.0
            result_andi = await run_retrieval_metrics(
                session,
                dataset_id=ds.id,
                embedder=FakeEmbedder(),
                user=andi,
                created_by=f"user:{owner.id}",
            )
            assert result_andi.adapter == "retrieval-metrics.local"
            assert result_andi.status == "completed"
            assert result_andi.metrics["overall"]["recall_at_k"] == 1.0
            assert result_andi.metrics["overall"]["mrr"] == 1.0
            assert result_andi.metrics["overall"]["ndcg_at_k"] == 1.0
            assert "en" in result_andi.metrics["slices"]
            assert result_andi.metrics["slices"]["en"]["recall_at_k"] == 1.0

            # Budi cannot see rev_doc -> recall@5 = 0.0 (no leak)
            result_budi = await run_retrieval_metrics(
                session,
                dataset_id=ds.id,
                embedder=FakeEmbedder(),
                user=budi,
                created_by=f"user:{owner.id}",
            )
            assert result_budi.metrics["overall"]["recall_at_k"] == 0.0
            assert result_budi.metrics["overall"]["mrr"] == 0.0

            # Item results never contain restricted text or document titles
            for ir in result_budi.item_results:
                assert "Revenue Report" not in str(ir)
                assert "30 percent" not in str(ir)
                assert "HR Policy" not in str(ir)

    _migrate()
    asyncio.run(run())


def test_runner_cross_lingual_slices():
    """Runner aggregates cross-lingual slices correctly with permission filtering."""

    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi, _budi = await _users(session)

            doc = await create_seeded_document(
                session, owner=owner, title="Revenue Report EN",
                text="The revenue share is 30 percent.", page=4,
            )
            await share_document(session, RecordingAuthz(), actor=owner,
                                 document_id=doc.id, principal=f"user:{andi.id}")
            await index_document_chunks(session, embedder=FakeEmbedder(), document_id=doc.id)

            ds = await create_dataset(
                session,
                name="cross-lingual-smoke",
                items=[
                    {
                        "question": "Berapa revenue share?",
                        "relevant_document_ids": [str(doc.id)],
                        "language_slice": "id_question_en_source",
                        "k": 5,
                    },
                    {
                        "question": "What is the revenue?",
                        "relevant_document_ids": [str(doc.id)],
                        "language_slice": "en",
                        "k": 5,
                    },
                ],
                source="manual",
                created_by=f"user:{owner.id}",
            )

            result = await run_retrieval_metrics(
                session, dataset_id=ds.id, embedder=FakeEmbedder(),
                user=andi, created_by=f"user:{owner.id}",
            )

            assert "id_question_en_source" in result.metrics["slices"]
            assert "en" in result.metrics["slices"]
            assert result.metrics["slices"]["en"]["count"] == 1
            assert result.metrics["slices"]["id_question_en_source"]["count"] == 1
            assert result.metrics["overall"]["count"] == 2

    _migrate()
    asyncio.run(run())


def test_adapter_protocol_compatible_with_eval_lab():
    """RetrievalMetricsAdapter satisfies the EvalAdapter protocol shape."""

    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi, _budi = await _users(session)

            doc = await create_seeded_document(
                session, owner=owner, title="Revenue Report",
                text="The revenue share is 30 percent.", page=4,
            )
            await share_document(session, RecordingAuthz(), actor=owner,
                                 document_id=doc.id, principal=f"user:{andi.id}")
            await index_document_chunks(session, embedder=FakeEmbedder(), document_id=doc.id)

            adapter = RetrievalMetricsAdapter(
                session=session, embedder=FakeEmbedder(), user=andi,
            )
            assert adapter.name == "retrieval-metrics.local"
            items = [
                {
                    "question": "What is the revenue share?",
                    "relevant_document_ids": [str(doc.id)],
                    "language_slice": "en",
                    "k": 5,
                },
            ]
            metrics, item_results = await adapter.evaluate(items)
            assert "overall" in metrics
            assert "slices" in metrics
            assert len(item_results) == 1
            assert "recall_at_k" in item_results[0]

    _migrate()
    asyncio.run(run())
