"""NFR-20: idempotency keys for create operations (replay, conflict, per-principal scope)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from e2eai.core.idempotency import IdempotencyMiddleware, MemoryIdempotencyStore


def _app(store=None):
    app = FastAPI()
    calls = {"n": 0}

    @app.post("/things")
    async def create(payload: dict):
        calls["n"] += 1
        return {"id": calls["n"], "name": payload.get("name")}

    @app.post("/boom")
    async def boom():
        calls["n"] += 1
        raise RuntimeError("x")

    @app.get("/things")
    async def lst():
        calls["n"] += 1
        return {"n": calls["n"]}

    app.add_middleware(IdempotencyMiddleware, store=store or MemoryIdempotencyStore())
    return TestClient(app, raise_server_exceptions=False), calls


def test_same_key_and_body_replays_first_response_without_rerunning():
    c, calls = _app()
    h = {"Idempotency-Key": "key-1", "Authorization": "Bearer a"}
    r1 = c.post("/things", json={"name": "x"}, headers=h)
    r2 = c.post("/things", json={"name": "x"}, headers=h)
    assert r1.json() == r2.json() == {"id": 1, "name": "x"}
    assert calls["n"] == 1
    assert r2.headers["idempotent-replayed"] == "true"
    assert "idempotent-replayed" not in r1.headers


def test_same_key_with_different_body_is_rejected_422_problem():
    c, calls = _app()
    h = {"Idempotency-Key": "key-2", "Authorization": "Bearer a"}
    c.post("/things", json={"name": "x"}, headers=h)
    r = c.post("/things", json={"name": "y"}, headers=h)
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["title_id"] == "Kunci idempotensi dipakai ulang"
    assert calls["n"] == 1


def test_key_is_scoped_per_principal():
    c, calls = _app()
    a = c.post("/things", json={"name": "x"}, headers={"Idempotency-Key": "k", "Authorization": "Bearer a"})
    b = c.post("/things", json={"name": "x"}, headers={"Idempotency-Key": "k", "Authorization": "Bearer b"})
    assert a.json()["id"] == 1 and b.json()["id"] == 2
    assert calls["n"] == 2


def test_without_key_or_for_get_nothing_is_cached():
    c, calls = _app()
    c.post("/things", json={}, headers={"Authorization": "Bearer a"})
    c.post("/things", json={}, headers={"Authorization": "Bearer a"})
    c.get("/things", headers={"Idempotency-Key": "g", "Authorization": "Bearer a"})
    c.get("/things", headers={"Idempotency-Key": "g", "Authorization": "Bearer a"})
    assert calls["n"] == 4


def test_server_errors_are_not_cached_so_client_can_retry():
    c, calls = _app()
    h = {"Idempotency-Key": "b", "Authorization": "Bearer a"}
    assert c.post("/boom", headers=h).status_code == 500
    assert c.post("/boom", headers=h).status_code == 500
    assert calls["n"] == 2


def test_malformed_key_is_rejected():
    c, calls = _app()
    r = c.post("/things", json={}, headers={"Idempotency-Key": "bad key!" * 20, "Authorization": "Bearer a"})
    assert r.status_code == 422
    assert calls["n"] == 0


def test_store_failure_degrades_to_normal_processing():
    class Broken:
        async def get(self, k):
            raise ConnectionError("down")

        async def put(self, k, v, ttl):
            raise ConnectionError("down")

    c, calls = _app(Broken())
    r = c.post("/things", json={"name": "x"}, headers={"Idempotency-Key": "k", "Authorization": "Bearer a"})
    assert r.status_code == 200 and calls["n"] == 1


def test_raw_key_and_credentials_are_not_stored_in_clear():
    store = MemoryIdempotencyStore()
    c, _ = _app(store)
    c.post("/things", json={"name": "x"}, headers={"Idempotency-Key": "my-secret-key", "Authorization": "Bearer tok123"})
    dump = repr(store.data)
    assert "my-secret-key" not in dump and "tok123" not in dump


def test_same_key_in_flight_duplicate_is_rejected_without_second_write():
    """Concurrent duplicate create requests must not both reach the app before replay is cached."""
    import asyncio

    async def scenario():
        store = MemoryIdempotencyStore()
        started = asyncio.Event()
        release = asyncio.Event()
        calls = {"n": 0}

        async def slow_app(scope, receive, send):
            calls["n"] += 1
            started.set()
            await release.wait()
            body = b'{"ok":true}'
            await send({
                "type": "http.response.start",
                "status": 201,
                "headers": [(b"content-type", b"application/json")],
            })
            await send({"type": "http.response.body", "body": body})

        app = IdempotencyMiddleware(slow_app, store=store)

        async def request():
            messages = [{"type": "http.request", "body": b'{"name":"x"}', "more_body": False}]
            sent = []
            scope = {
                "type": "http",
                "method": "POST",
                "path": "/things",
                "headers": [
                    (b"idempotency-key", b"same-key"),
                    (b"authorization", b"Bearer user-a"),
                    (b"content-type", b"application/json"),
                ],
            }

            async def receive():
                return messages.pop(0) if messages else {"type": "http.request", "body": b"", "more_body": False}

            async def send(message):
                sent.append(message)

            await app(scope, receive, send)
            return sent

        first = asyncio.create_task(request())
        await asyncio.wait_for(started.wait(), timeout=1)
        second = asyncio.create_task(request())
        await asyncio.sleep(0.05)
        release.set()
        first_sent = await asyncio.wait_for(first, timeout=1)
        second_sent = await asyncio.wait_for(second, timeout=1)
        return first_sent, second_sent, calls["n"], repr(store.data)

    first_sent, second_sent, call_count, store_dump = asyncio.run(scenario())
    assert first_sent[0]["status"] == 201
    assert second_sent[0]["status"] == 409
    assert second_sent[0]["headers"][-1] == (b"retry-after", b"1")
    assert call_count == 1
    assert "same-key" not in store_dump and "Bearer user-a" not in store_dump
