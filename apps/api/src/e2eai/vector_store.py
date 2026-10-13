"""FR-R3: `VectorStore` port (pgvector P0, Qdrant P1) with a contract check any implementation must pass.

Rules that hold for every implementation (FR-C1/FR-C2):
- The permission filter travels *inside* the query: `VectorQuery.allowed_document_ids` is mandatory, an empty
  set returns nothing and never contacts the backend, and nothing is filtered after top-k.
- Only ids and vectors are stored in the vector backend (chunk text and titles stay in Postgres), so the
  backend never holds content that could be shown without a permission check.
- pgvector is served natively by `retrieval.retrieve_relevant_chunks` (the filter is a SQL predicate joined with
  `doc_principals`), so `make_vector_store("pgvector")` returns None. The port covers the P1 swap targets.
- External calls use bounded retry and a circuit breaker; failures surface as a clear 503 with no host,
  key, or exception text (NFR-19).
"""

from __future__ import annotations

import asyncio
import math
import uuid
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from .core.errors import AppError
from .core.resilience import RETRY_STATUS, TRANSIENT, RetryExhausted, breaker_for, with_retry


@dataclass(frozen=True)
class VectorPoint:
    chunk_id: str
    document_id: str
    vector: Sequence[float]


@dataclass(frozen=True)
class VectorHit:
    chunk_id: str
    document_id: str
    score: float


@dataclass(frozen=True)
class VectorQuery:
    vector: Sequence[float]
    allowed_document_ids: set[str]
    limit: int = 4

    def __post_init__(self):
        if self.allowed_document_ids is None:  # fail closed: no filter is never "everything"
            raise ValueError("allowed_document_ids is required")
        if self.limit < 1:
            raise ValueError("limit must be >= 1")


class VectorStore(Protocol):
    async def upsert(self, points: Sequence[VectorPoint]) -> None: ...

    async def delete_documents(self, document_ids: Iterable[str]) -> None: ...

    async def query(self, q: VectorQuery) -> list[VectorHit]: ...


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


class InMemoryVectorStore:
    """Deterministic reference implementation for tests and the contract."""

    def __init__(self) -> None:
        self._points: dict[str, VectorPoint] = {}

    async def upsert(self, points: Sequence[VectorPoint]) -> None:
        for p in points:
            self._points[p.chunk_id] = p

    async def delete_documents(self, document_ids: Iterable[str]) -> None:
        gone = set(document_ids)
        self._points = {k: p for k, p in self._points.items() if p.document_id not in gone}

    async def query(self, q: VectorQuery) -> list[VectorHit]:
        if not q.allowed_document_ids:
            return []
        hits = [
            VectorHit(p.chunk_id, p.document_id, _cosine(q.vector, p.vector))
            for p in self._points.values()
            if p.document_id in q.allowed_document_ids
        ]
        hits.sort(key=lambda h: -h.score)
        return hits[: q.limit]


@dataclass
class QdrantVectorStore:
    """Qdrant REST adapter (P1). Payload holds ids only; the permission filter is part of the search request."""

    base_url: str
    api_key: str = field(repr=False)
    collection: str
    dims: int = 0  # 0 = take the size from the first upserted vector
    timeout: float = 30.0
    client_factory: Callable[..., Any] = httpx.AsyncClient
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    attempts: int = 3
    _ready: bool = field(default=False, init=False, repr=False)

    async def _call(self, method: str, path: str, body: dict) -> dict:
        breaker = breaker_for(f"{self.base_url}/{self.collection}", "vector-store")
        if not breaker.allow():
            raise AppError(503, "Upstream service unavailable",
                           "The search index is temporarily unavailable. Please try again shortly.",
                           "upstream-unavailable", headers={"Retry-After": str(breaker.retry_after())})

        async def once():
            headers = {"api-key": self.api_key} if self.api_key else {}
            async with self.client_factory(base_url=self.base_url, timeout=self.timeout) as client:
                response = await getattr(client, method.lower())(path, headers=headers, json=body)
            status = getattr(response, "status_code", 200)
            if status in RETRY_STATUS:
                raise ConnectionError("retryable upstream status")
            return response

        try:
            response = await with_retry(once, attempts=self.attempts, timeout=None,
                                        retry_on=TRANSIENT + (httpx.TransportError,), sleep=self.sleep)
        except RetryExhausted:
            breaker.record_failure()
            raise AppError(503, "Upstream service unavailable",
                           "The search index did not respond. Please try again shortly.",
                           "upstream-unavailable") from None
        breaker.record_success()  # the service answered; a 4xx is a request problem, not an outage
        status = getattr(response, "status_code", 200)
        if status == 409 and method == "PUT":
            return {}  # collection already exists
        if status >= 400:
            raise AppError(502, "Search index rejected the request", "", "upstream-error")
        return response.json()

    async def _ensure_collection(self, size: int | None = None) -> None:
        if not self._ready:
            dims = self.dims or size
            if not dims:
                return  # nothing indexed yet: there is no collection to touch
            await self._call("PUT", f"/collections/{self.collection}",
                             {"vectors": {"size": dims, "distance": "Cosine"}})
            self._ready = True

    async def upsert(self, points: Sequence[VectorPoint]) -> None:
        if not points:
            return
        await self._ensure_collection(len(points[0].vector))
        await self._call("PUT", f"/collections/{self.collection}/points?wait=true", {"points": [
            {"id": p.chunk_id, "vector": [float(x) for x in p.vector],
             "payload": {"chunk_id": p.chunk_id, "document_id": p.document_id}}
            for p in points
        ]})

    async def delete_documents(self, document_ids: Iterable[str]) -> None:
        ids = sorted(set(document_ids))
        if not ids:
            return
        await self._ensure_collection()
        await self._call("POST", f"/collections/{self.collection}/points/delete?wait=true",
                         {"filter": {"must": [{"key": "document_id", "match": {"any": ids}}]}})

    async def query(self, q: VectorQuery) -> list[VectorHit]:
        if not q.allowed_document_ids:
            return []  # empty permission set: nothing to search, no request made
        data = await self._call("POST", f"/collections/{self.collection}/points/search", {
            "vector": [float(x) for x in q.vector],
            "filter": {"must": [{"key": "document_id", "match": {"any": sorted(q.allowed_document_ids)}}]},
            "limit": q.limit,
            "with_payload": True,
        })
        return [
            VectorHit(str(h["payload"]["chunk_id"]), str(h["payload"]["document_id"]), float(h["score"]))
            for h in data.get("result", [])
        ]


_CONFIGURED: dict[tuple[str, str, str], VectorStore] = {}


def configured_vector_store(settings: Any = None) -> VectorStore | None:
    """The store chosen by `components.vector_store` (None = pgvector, served by SQL). Adapters are cached per
    endpoint so the circuit breaker and collection state are shared across requests."""
    from .core.config import get_settings

    settings = settings or get_settings()
    if settings.vector_store == "pgvector":
        return None
    key = (settings.vector_store, settings.qdrant_url, "e2eai_chunks")
    if key not in _CONFIGURED:
        store = make_vector_store(settings.vector_store, base_url=settings.qdrant_url,
                                  api_key=settings.qdrant_api_key, collection="e2eai_chunks")
        assert store is not None
        _CONFIGURED[key] = store
    return _CONFIGURED[key]


def make_vector_store(name: str, **kwargs: Any) -> VectorStore | None:
    """Build a store by name. ``pgvector`` is served by the SQL retrieval path and returns None."""
    if name == "pgvector":
        return None
    if name == "memory":
        return InMemoryVectorStore()
    if name == "qdrant":
        return QdrantVectorStore(**kwargs)
    raise ValueError(f"unknown vector store: {name!r}")


async def check_vector_store_contract(store: VectorStore) -> list[str]:
    """Return contract failures for ``store`` (empty list = conforms). Uses only synthetic ids and vectors."""
    dims = max(2, int(getattr(store, "dims", 2)))

    def vec(i: int, bias: float = 0.0) -> list[float]:
        v = [0.0] * dims
        v[i] = 1.0
        v[(i + 1) % dims] = bias
        return v

    failures: list[str] = []
    doc_a, doc_b = str(uuid.uuid4()), str(uuid.uuid4())
    a1, a2, b1 = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    await store.upsert([
        VectorPoint(a1, doc_a, vec(0)),
        VectorPoint(a2, doc_a, vec(1)),
        VectorPoint(b1, doc_b, vec(0, 0.1)),
    ])

    both = await store.query(VectorQuery(vec(0), {doc_a, doc_b}, limit=5))
    if [h.chunk_id for h in both][:1] != [a1]:
        failures.append("nearest chunk must rank first")
    if any(both[i].score < both[i + 1].score for i in range(len(both) - 1)):
        failures.append("hits must be ordered best-first")
    if len(await store.query(VectorQuery(vec(0), {doc_a, doc_b}, limit=1))) != 1:
        failures.append("limit must be respected")

    only_a = await store.query(VectorQuery(vec(0), {doc_a}, limit=5))
    if any(h.document_id != doc_a for h in only_a) or not only_a:
        failures.append("permission filter must apply inside the query (documents outside the allowed set returned)")
    if await store.query(VectorQuery(vec(0), set(), limit=5)):
        failures.append("empty permission filter must return nothing")

    await store.upsert([VectorPoint(a1, doc_a, vec(1))])  # same chunk id replaces, never duplicates
    again = await store.query(VectorQuery(vec(1), {doc_a}, limit=5))
    if sum(1 for h in again if h.chunk_id == a1) != 1:
        failures.append("upsert must be idempotent per chunk id")

    await store.delete_documents([doc_a])
    after = await store.query(VectorQuery(vec(0), {doc_a, doc_b}, limit=5))
    if any(h.document_id == doc_a for h in after):
        failures.append("deleted document must no longer be returned")
    await store.delete_documents([doc_b])
    return failures
