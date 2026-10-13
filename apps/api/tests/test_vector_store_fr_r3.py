"""FR-R3: VectorStore port (pgvector P0 / Qdrant P1). The permission filter travels inside the query (FR-C2)."""

import asyncio
import math
import uuid

import httpx
import pytest

from e2eai.core.errors import AppError
from e2eai.core.resilience import breaker_states, reset_breakers
from e2eai.vector_store import (
    InMemoryVectorStore,
    QdrantVectorStore,
    VectorPoint,
    VectorQuery,
    check_vector_store_contract,
    make_vector_store,
)


def run(coro):
    return asyncio.run(coro)


class FakeQdrant:
    """Tiny Qdrant REST double: honours `must/match` filters and cosine scoring."""

    def __init__(self, fail=False):
        self.collections: dict[str, dict] = {}
        self.requests: list[tuple[str, str, dict]] = []
        self.fail = fail

    def factory(self, **kwargs):
        return _Client(self)

    def handle(self, method, path, body):
        self.requests.append((method, path, body))
        if self.fail:
            raise httpx.ConnectError("boom http://secret-host:6333")
        parts = path.split("?")[0].strip("/").split("/")
        coll = self.collections.setdefault(parts[1], {})
        if method == "PUT" and len(parts) == 2:
            return {"result": True}
        if method == "PUT" and parts[2] == "points":
            for p in body["points"]:
                coll[p["id"]] = p
            return {"result": {"status": "acknowledged"}}
        if parts[-1] == "delete":
            keep = {i: p for i, p in coll.items() if not _matches(p["payload"], body["filter"])}
            coll.clear()
            coll.update(keep)
            return {"result": {"status": "acknowledged"}}
        if parts[-1] == "search":
            hits = [
                {"id": p["id"], "score": _cos(body["vector"], p["vector"]), "payload": p["payload"]}
                for p in coll.values()
                if _matches(p["payload"], body.get("filter"))
            ]
            hits.sort(key=lambda h: -h["score"])
            return {"result": hits[: body["limit"]]}
        raise AssertionError(path)


def _matches(payload, flt):
    if not flt:
        return True
    for cond in flt.get("must", []):
        m = cond["match"]
        v = payload.get(cond["key"])
        if "any" in m and v not in m["any"]:
            return False
        if "value" in m and v != m["value"]:
            return False
    return True


def _cos(a, b):
    return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


class _Response:
    def __init__(self, data):
        self.status_code = 200
        self._data = data

    def json(self):
        return self._data

    def raise_for_status(self):
        pass


class _Client:
    def __init__(self, server):
        self.server = server

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def put(self, path, headers=None, json=None):
        return _Response(self.server.handle("PUT", path, json or {}))

    async def post(self, path, headers=None, json=None):
        return _Response(self.server.handle("POST", path, json or {}))


def qdrant(server, **kw):
    return QdrantVectorStore(base_url="http://qdrant.invalid:6333", api_key="k", collection="chunks", dims=2,
                             client_factory=server.factory, sleep=_nosleep, **kw)


async def _nosleep(_):
    return None


def test_in_memory_store_passes_contract():
    assert run(check_vector_store_contract(InMemoryVectorStore())) == []


def test_qdrant_adapter_passes_contract_against_rest_double():
    server = FakeQdrant()
    assert run(check_vector_store_contract(qdrant(server))) == []


def test_contract_catches_a_store_that_ignores_the_permission_filter():
    class Leaky(InMemoryVectorStore):
        async def query(self, q):
            return await super().query(VectorQuery(vector=q.vector, allowed_document_ids=set(self._all_docs()), limit=q.limit))

        def _all_docs(self):
            return {p.document_id for p in self._points.values()}

    failures = run(check_vector_store_contract(Leaky()))
    assert any("filter" in f for f in failures)


def test_missing_allowed_set_fails_closed_and_empty_set_returns_nothing_without_a_call():
    server = FakeQdrant()
    store = qdrant(server)
    with pytest.raises(ValueError):
        VectorQuery(vector=[1.0, 0.0], allowed_document_ids=None)  # type: ignore[arg-type]
    assert run(store.query(VectorQuery(vector=[1.0, 0.0], allowed_document_ids=set()))) == []
    assert server.requests == []  # no request is made for an empty permission set


def test_qdrant_query_carries_the_filter_inside_the_search_and_no_text_in_payload():
    server = FakeQdrant()
    store = qdrant(server)
    d1, d2 = str(uuid.uuid4()), str(uuid.uuid4())
    run(store.upsert([
        VectorPoint(chunk_id=str(uuid.uuid4()), document_id=d1, vector=[1.0, 0.0]),
        VectorPoint(chunk_id=str(uuid.uuid4()), document_id=d2, vector=[1.0, 0.1]),
    ]))
    hits = run(store.query(VectorQuery(vector=[1.0, 0.0], allowed_document_ids={d1}, limit=5)))
    assert [h.document_id for h in hits] == [d1]
    method, path, body = [r for r in server.requests if r[1].endswith("/search")][0]
    assert body["filter"] == {"must": [{"key": "document_id", "match": {"any": [d1]}}]}
    stored = [r for r in server.requests if r[0] == "PUT" and "points" in r[1]][0][2]
    assert set(stored["points"][0]["payload"]) == {"chunk_id", "document_id"}  # chunk text stays in Postgres


def test_qdrant_outage_is_a_clear_503_without_host_and_trips_the_breaker():
    reset_breakers()
    server = FakeQdrant(fail=True)
    store = qdrant(server)
    for _ in range(5):
        with pytest.raises(AppError) as exc:
            run(store.query(VectorQuery(vector=[1.0, 0.0], allowed_document_ids={"d"})))
        assert exc.value.status == 503
        assert "qdrant" not in str(exc.value.detail).lower() and "secret-host" not in str(exc.value.detail)
    assert breaker_states()["vector-store"] == 2
    calls = len(server.requests)
    with pytest.raises(AppError) as exc:
        run(store.query(VectorQuery(vector=[1.0, 0.0], allowed_document_ids={"d"})))
    assert exc.value.headers and "Retry-After" in exc.value.headers
    assert len(server.requests) == calls  # open breaker: upstream not contacted
    reset_breakers()


def test_factory_selects_store_by_name():
    assert isinstance(make_vector_store("memory"), InMemoryVectorStore)
    assert isinstance(
        make_vector_store("qdrant", base_url="http://q:6333", api_key="k", collection="c", dims=2), QdrantVectorStore
    )
    assert make_vector_store("pgvector") is None  # served by retrieval.retrieve_relevant_chunks (SQL-native predicate)
    with pytest.raises(ValueError):
        make_vector_store("nope")
