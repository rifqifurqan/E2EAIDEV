"""Deterministic document data-quality checks (FR-D7).

The helpers are intentionally pure/offline so ingestion, admin dashboards, and
future scheduled audits can reuse the same checks without touching external
services.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from typing import Any

_WORD_RE = re.compile(r"[a-z0-9]+")
_UNPARSEABLE_STATUSES = {"unparseable", "failed", "parse_failed", "error"}


def _title_text(document: dict[str, Any]) -> str:
    return str(document.get("title") or "").strip()


def _normalized_title_tokens(title: str) -> tuple[str, ...]:
    """Normalize a title to comparable tokens for duplicate detection."""
    return tuple(sorted(_WORD_RE.findall(title.casefold())))


def _token_similarity(left: tuple[str, ...], right: tuple[str, ...]) -> float:
    if not left or not right:
        return 0.0
    a = set(left)
    b = set(right)
    return len(a & b) / len(a | b)


def find_duplicate_titles(
    documents: list[dict[str, Any]], *, near_threshold: float = 0.88
) -> list[list[int]]:
    """Return index groups whose titles are duplicate or near-duplicate.

    Matching is permission-neutral and metadata-only: titles are normalized by
    case/spacing/punctuation and compared by token overlap. Returned indexes
    refer to the input order so callers can map them back to records safely.
    Blank titles are ignored.
    """
    groups: list[list[int]] = []
    assigned: set[int] = set()
    normalized: list[tuple[int, tuple[str, ...]]] = []

    exact: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for index, document in enumerate(documents):
        tokens = _normalized_title_tokens(_title_text(document))
        if not tokens:
            continue
        exact[tokens].append(index)
        normalized.append((index, tokens))

    for indexes in exact.values():
        if len(indexes) > 1:
            groups.append(indexes)
            assigned.update(indexes)

    for index, tokens in normalized:
        if index in assigned:
            continue
        near = [index]
        for other_index, other_tokens in normalized:
            if other_index <= index or other_index in assigned:
                continue
            if _token_similarity(tokens, other_tokens) >= near_threshold:
                near.append(other_index)
        if len(near) > 1:
            groups.append(near)
            assigned.update(near)

    return groups


def is_stale_document(mtime: datetime | None, *, now: datetime, max_age_days: int) -> bool:
    """Return whether a document is missing freshness metadata or too old."""
    if mtime is None:
        return True
    age_seconds = (now - mtime).total_seconds()
    return age_seconds > max_age_days * 24 * 60 * 60


def is_unparseable(file_status: str | None, *, parse_error: str | None = None) -> bool:
    """Return whether ingestion/parser state indicates an unparseable file."""
    status = (file_status or "").strip().casefold()
    return status in _UNPARSEABLE_STATUSES or bool((parse_error or "").strip())
