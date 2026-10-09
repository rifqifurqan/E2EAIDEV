"""Retrieval metrics lab helpers (FR-R8).

Computes recall@k, MRR, and nDCG@k over the existing permission-filtered retrieval path.
Stored item results intentionally contain IDs and metric numbers only, not retrieved snippets or
restricted titles, so the eval run cannot become a side channel.
"""

from __future__ import annotations

import math
import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from .authz import principals
from .core.errors import AppError
from .db import EvalDataset, EvalRun, User
from .retrieval import Embedder, retrieve_relevant_chunks


def _as_set(values: Sequence[str] | set[str] | None) -> set[str]:
    return {str(value) for value in (values or []) if value is not None}


def compute_recall_at_k(retrieved_ids: Sequence[str], relevant_ids: set[str], k: int) -> float:
    """recall@k = relevant retrieved in top-k / relevant total."""
    if not relevant_ids:
        return 0.0
    top_k = set(str(value) for value in list(retrieved_ids)[: max(0, int(k))])
    return round(len(top_k & relevant_ids) / len(relevant_ids), 4)


def compute_mrr(retrieved_ids: Sequence[str], relevant_ids: set[str]) -> float:
    """Mean reciprocal rank for a single query."""
    if not relevant_ids:
        return 0.0
    for index, doc_id in enumerate(retrieved_ids, start=1):
        if str(doc_id) in relevant_ids:
            return round(1.0 / index, 4)
    return 0.0


def compute_ndcg_at_k(retrieved_ids: Sequence[str], relevant_ids: set[str], k: int) -> float:
    """Binary-relevance nDCG@k."""
    if not relevant_ids:
        return 0.0
    top = [str(value) for value in list(retrieved_ids)[: max(0, int(k))]]
    dcg = 0.0
    for index, doc_id in enumerate(top, start=1):
        if doc_id in relevant_ids:
            dcg += 1.0 / math.log2(index + 1)
    ideal_hits = min(len(relevant_ids), max(0, int(k)))
    if ideal_hits == 0:
        return 0.0
    idcg = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_hits + 1))
    return round(dcg / idcg, 4) if idcg else 0.0


def _average(items: Sequence[dict], key: str) -> float:
    if not items:
        return 0.0
    return round(sum(float(item.get(key, 0.0)) for item in items) / len(items), 4)


def aggregate_by_slice(item_results: Sequence[dict]) -> dict[str, dict]:
    """Aggregate metrics by language/cross-lingual slice label."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in item_results:
        grouped[str(item.get("language_slice") or "unspecified")].append(item)
    return {
        label: {
            "count": len(rows),
            "recall_at_k": _average(rows, "recall_at_k"),
            "mrr": _average(rows, "mrr"),
            "ndcg_at_k": _average(rows, "ndcg_at_k"),
        }
        for label, rows in sorted(grouped.items())
    }


@dataclass
class RetrievalMetricsAdapter:
    """EvalAdapter-compatible retrieval metrics adapter."""

    session: AsyncSession
    embedder: Embedder
    user: User
    name: str = "retrieval-metrics.local"

    async def evaluate(self, items: Sequence[dict]) -> tuple[dict, list[dict]]:
        principal_list = await principals(self.session, self.user)
        item_results: list[dict] = []
        for index, item in enumerate(items):
            question = str(item.get("question") or "").strip()
            if not question:
                raise AppError(400, "Retrieval metric question is required")
            k = int(item.get("k") or 5)
            relevant_doc_ids = _as_set(item.get("relevant_document_ids"))
            relevant_chunk_ids = _as_set(item.get("relevant_chunk_ids"))
            # Current retrieval returns document IDs; chunk IDs can be supported later without changing schema.
            relevant_ids = relevant_doc_ids or relevant_chunk_ids
            retrieved = await retrieve_relevant_chunks(
                self.session,
                embedder=self.embedder,
                user_principals=principal_list,
                question=question,
                limit=k,
                user=self.user,
            )
            retrieved_doc_ids = [str(row.get("document_id")) for row in retrieved if row.get("document_id")]
            unique_ranked_doc_ids = list(dict.fromkeys(retrieved_doc_ids))
            result = {
                "index": index,
                "language_slice": str(item.get("language_slice") or "unspecified"),
                "k": k,
                "retrieved_document_ids": unique_ranked_doc_ids,
                "retrieved_count": len(unique_ranked_doc_ids),
                "relevant_count": len(relevant_ids),
                "recall_at_k": compute_recall_at_k(unique_ranked_doc_ids, relevant_ids, k),
                "mrr": compute_mrr(unique_ranked_doc_ids, relevant_ids),
                "ndcg_at_k": compute_ndcg_at_k(unique_ranked_doc_ids, relevant_ids, k),
            }
            item_results.append(result)

        overall = {
            "count": len(item_results),
            "recall_at_k": _average(item_results, "recall_at_k"),
            "mrr": _average(item_results, "mrr"),
            "ndcg_at_k": _average(item_results, "ndcg_at_k"),
        }
        return {"overall": overall, "slices": aggregate_by_slice(item_results)}, item_results


async def run_retrieval_metrics(
    session: AsyncSession,
    *,
    dataset_id: uuid.UUID,
    embedder: Embedder,
    user: User,
    created_by: str,
) -> EvalRun:
    """Run retrieval metrics for one dataset and persist an EvalRun."""
    ds = await session.get(EvalDataset, dataset_id)
    if ds is None:
        raise AppError(404, "Dataset not found")
    adapter = RetrievalMetricsAdapter(session=session, embedder=embedder, user=user)
    metrics, item_results = await adapter.evaluate(ds.items)
    run = EvalRun(
        dataset_id=ds.id,
        adapter=adapter.name,
        status="completed",
        metrics=metrics,
        item_results=item_results,
        created_by=created_by,
    )
    session.add(run)
    await session.commit()
    return run
