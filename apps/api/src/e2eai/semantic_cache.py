"""Semantic and prompt cache helpers keyed by permission set (FR-M4).

The cache key is deliberately opaque: it contains hashes of the normalized prompt and sorted
permission principals plus safe version/model dimensions. It never stores raw prompts, answers,
document text, tokens, secrets, or principal identifiers in keys or metadata.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterable


_CACHE_PREFIX = "fr-m4"
_NON_WORD = re.compile(r"[^a-z0-9]+")


def _sha256_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_question(question: str) -> str:
    """Normalize a question for deterministic offline cache identity.

    This is an exact-normalized prompt hash, not a vector similarity engine. Later live semantic
    caches can replace this boundary with an embedding index while preserving the permission hash.
    """
    text = _NON_WORD.sub(" ", question.lower()).strip()
    return " ".join(text.split())


def permission_set_hash(principals: Iterable[str]) -> str:
    """Return a stable opaque hash of a user's permission principals.

    Sorting makes the hash order independent. Empty/duplicate principals normalize to one canonical
    set. The raw principal strings never appear in the returned value.
    """
    canonical = sorted({str(p).strip() for p in principals if str(p).strip()})
    return _sha256_json({"principals": canonical})


@dataclass(frozen=True)
class CacheContext:
    """Safe dimensions that make an answer cache entry reusable.

    ``principals`` are accepted only to compute ``permission_hash``; they are not exposed by keys or
    metadata. Version fields default to ``default`` so tests and offline callers can use the helper
    before full bot/index registries are present.
    """

    principals: Iterable[str]
    bot_version: str = "default"
    index_version: str = "default"
    prompt_version: str = "default"
    model: str = "default"
    retrieval_mode: str = "dense"
    scope: str = "all"
    document_id: str | None = None

    @property
    def permission_hash(self) -> str:
        return permission_set_hash(self.principals)

    def safe_dimensions(self) -> dict[str, Any]:
        return {
            "permission_hash": self.permission_hash,
            "bot_version": self.bot_version or "default",
            "index_version": self.index_version or "default",
            "prompt_version": self.prompt_version or "default",
            "model": self.model or "default",
            "retrieval_mode": self.retrieval_mode or "dense",
            "scope": self.scope or "all",
            "document_id_hash": _sha256_json({"document_id": self.document_id}) if self.document_id else None,
        }


def build_prompt_cache_key(question: str, context: CacheContext) -> str:
    """Build a safe prompt/semantic cache key for one permission-scoped answer path."""
    dimensions = context.safe_dimensions()
    dimensions["question_hash"] = _sha256_json({"question": _normalize_question(question)})
    return f"{_CACHE_PREFIX}:{_sha256_json(dimensions)}"


class SemanticPromptCache:
    """Small deterministic cache boundary for FR-M4 tests and local/offline answer paths.

    Production deployments can swap this for Redis/vector-backed semantic cache using the same key
    helpers. Values may contain answers/citations because they are returned only after a key hit;
    keys and metadata remain safe and permission-scoped.
    """

    def __init__(self) -> None:
        self._entries: dict[str, dict[str, Any]] = {}

    def get(self, question: str, context: CacheContext) -> dict[str, Any] | None:
        entry = self._entries.get(build_prompt_cache_key(question, context))
        return deepcopy(entry["value"]) if entry else None

    def put(self, question: str, context: CacheContext, value: dict[str, Any]) -> None:
        key = build_prompt_cache_key(question, context)
        self._entries[key] = {
            "metadata": self.safe_metadata(question, context),
            "value": deepcopy(value),
        }

    def safe_metadata(self, question: str, context: CacheContext) -> dict[str, Any]:
        dimensions = context.safe_dimensions()
        dimensions["question_hash"] = _sha256_json({"question": _normalize_question(question)})
        dimensions["cache_key"] = build_prompt_cache_key(question, context)
        return dimensions

    def clear(self) -> None:
        self._entries.clear()
