"""Deterministic model routing for chat/model selection (FR-M3).

This module is intentionally pure and offline: it classifies query complexity with
stable rules so the serving layer can choose a smaller model for simple requests
and a larger/fallback model for complex or risky requests without an extra LLM call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_WORD_RE = re.compile(r"[a-zA-Z0-9_+-]+")
_TECHNICAL_KEYWORDS = frozenset({
    "api",
    "async",
    "auth",
    "authorization",
    "database",
    "debug",
    "docker",
    "error",
    "exception",
    "kubernetes",
    "migration",
    "oauth",
    "oidc",
    "postgres",
    "rollback",
    "sql",
    "sqlalchemy",
    "token",
    "traceback",
})
_REASONING_KEYWORDS = frozenset({
    "analyze",
    "bandingkan",
    "compare",
    "constraint",
    "constraints",
    "evaluate",
    "explain",
    "jelaskan",
    "multi-step",
    "plan",
    "propose",
    "reason",
    "risk",
    "strategy",
})


@dataclass(frozen=True)
class ModelRoutingConfig:
    """Small/large model routing thresholds.

    `large_model` is the safe fallback: empty queries or malformed inputs use it
    rather than routing to a cheaper/smaller model that may under-answer.
    """

    small_model: str = "qwen3.5:4b"
    large_model: str = "qwen3.5:14b"
    large_threshold: int = 7
    long_query_tokens: int = 48


def _tokens(query: str) -> list[str]:
    return [t.casefold() for t in _WORD_RE.findall(query)]


def classify_query_complexity(query: str) -> int:
    """Return a deterministic 0..10 query-complexity score."""
    terms = _tokens(query)
    if not terms:
        return 10

    score = 1
    count = len(terms)
    if count >= 80:
        score += 5
    elif count >= 48:
        score += 4
    elif count >= 28:
        score += 2

    keyword_hits = len(set(terms) & _TECHNICAL_KEYWORDS)
    reasoning_hits = len(set(terms) & _REASONING_KEYWORDS)
    score += min(keyword_hits * 2, 6)
    score += min(reasoning_hits, 3)

    if "?" in query and (" and " in query.casefold() or " lalu " in query.casefold()):
        score += 1

    return max(0, min(10, score))


def route_model(
    *,
    query: str,
    settings: ModelRoutingConfig | None = None,
    complexity_score: int | None = None,
) -> str:
    """Choose small or large model for a query with deterministic fallback rules."""
    cfg = settings or ModelRoutingConfig()
    score = classify_query_complexity(query) if complexity_score is None else max(0, min(10, complexity_score))
    if not query.strip():
        return cfg.large_model
    return cfg.large_model if score >= cfg.large_threshold else cfg.small_model
