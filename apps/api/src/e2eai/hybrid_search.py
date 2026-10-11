"""Hybrid search helpers (FR-R4): dense + sparse/BM25 fused with reciprocal rank fusion (RRF).

Pure, deterministic and offline. Callers pass candidates that were *already* permission-filtered
in SQL; this module only re-ranks them, so it can never widen access.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Hashable, Sequence

_TOKEN_RE = re.compile(r"[a-z0-9]+")

RRF_K = 60
BM25_K1 = 1.5
BM25_B = 0.75


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens."""
    return _TOKEN_RE.findall((text or "").lower())


def bm25_scores(query: str, documents: Sequence[str]) -> list[float]:
    """Okapi BM25 score of `query` against each document (corpus = `documents`)."""
    n = len(documents)
    if n == 0:
        return []
    q_terms = list(dict.fromkeys(tokenize(query)))
    tokenized = [tokenize(d) for d in documents]
    if not q_terms:
        return [0.0] * n
    avg_len = sum(len(t) for t in tokenized) / n or 1.0
    df = {term: sum(1 for toks in tokenized if term in toks) for term in q_terms}
    scores: list[float] = []
    for toks in tokenized:
        tf = Counter(toks)
        dl = len(toks)
        score = 0.0
        for term in q_terms:
            f = tf.get(term, 0)
            if not f:
                continue
            idf = math.log(1.0 + (n - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * (f * (BM25_K1 + 1)) / (f + BM25_K1 * (1 - BM25_B + BM25_B * dl / avg_len))
        scores.append(score)
    return scores


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[Hashable]], *, k: int = RRF_K
) -> list[tuple[Hashable, float]]:
    """Fuse ranked id lists: score(id) = sum 1/(k + rank). Ties keep first-seen order."""
    scores: dict[Hashable, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    # dicts preserve insertion order and sorted() is stable -> deterministic tie-break
    return sorted(scores.items(), key=lambda kv: -kv[1])


def fuse_dense_sparse(candidates: Sequence[dict], *, query: str, limit: int, k: int = RRF_K) -> list[dict]:
    """Re-rank dense-ordered `candidates` by RRF of dense order and BM25 order.

    Candidates must already be sorted best-first by dense similarity. Candidates with a zero
    BM25 score do not appear in the sparse ranking. Returns copies with `rrf_score` added.
    """
    items = list(candidates)
    if not items:
        return []
    sparse = bm25_scores(query, [c.get("text", "") for c in items])
    dense_rank = list(range(len(items)))
    sparse_rank = [i for i in sorted(range(len(items)), key=lambda i: -sparse[i]) if sparse[i] > 0]
    fused = reciprocal_rank_fusion([dense_rank, sparse_rank], k=k)
    return [{**items[int(i)], "rrf_score": round(score, 6)} for i, score in fused[:limit]]
