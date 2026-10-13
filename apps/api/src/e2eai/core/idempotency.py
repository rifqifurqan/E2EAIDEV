"""Idempotency keys for create operations (NFR-20).

Pure ASGI middleware. For POST/PUT/PATCH/DELETE requests carrying an ``Idempotency-Key`` header the first
completed (non-5xx) response is stored and replayed for the same key + same request body. A reused key with a
different body is rejected. Keys are scoped per principal (hash of credentials) and method + path; neither the
raw key nor credentials are stored. If the store is unavailable the request is processed normally (degrade,
never block writes).
"""

import asyncio
import base64
import hashlib
import json
import re
import time
from typing import Protocol

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}
KEY_RE = re.compile(r"[A-Za-z0-9._~:-]{1,128}")
DEFAULT_TTL = 24 * 3600
MAX_BODY = 1_000_000  # bodies/responses larger than this are processed normally, not cached
PROBLEM = b"application/problem+json"


class IdempotencyStore(Protocol):
    async def get(self, key: str) -> str | None: ...
    async def put(self, key: str, value: str, ttl: int) -> None: ...

    async def acquire_lock(self, key: str, value: str, ttl: int) -> str | None: ...
    async def release_lock(self, key: str, value: str) -> None: ...


class MemoryIdempotencyStore:
    def __init__(self) -> None:
        self.data: dict[str, tuple[str, float]] = {}
        self.locks: dict[str, tuple[str, float]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> str | None:
        item = self.data.get(key)
        if not item or item[1] < time.time():
            return None
        return item[0]

    async def put(self, key: str, value: str, ttl: int) -> None:
        self.data[key] = (value, time.time() + ttl)

    async def acquire_lock(self, key: str, value: str, ttl: int) -> str | None:
        async with self._lock:
            item = self.locks.get(key)
            now = time.time()
            if item and item[1] >= now:
                return item[0]
            self.locks[key] = (value, now + ttl)
            return None

    async def release_lock(self, key: str, value: str) -> None:
        async with self._lock:
            item = self.locks.get(key)
            if item and item[0] == value:
                self.locks.pop(key, None)


class ValkeyIdempotencyStore:
    def __init__(self, redis) -> None:
        self.redis = redis

    async def get(self, key: str) -> str | None:
        return await self.redis.get(f"idem:{key}")

    async def put(self, key: str, value: str, ttl: int) -> None:
        await self.redis.set(f"idem:{key}", value, ex=ttl)

    async def acquire_lock(self, key: str, value: str, ttl: int) -> str | None:
        lock_key = f"idemlock:{key}"
        acquired = await self.redis.set(lock_key, value, ex=ttl, nx=True)
        if acquired:
            return None
        return await self.redis.get(lock_key)

    async def release_lock(self, key: str, value: str) -> None:
        lock_key = f"idemlock:{key}"
        current = await self.redis.get(lock_key)
        if current == value:
            await self.redis.delete(lock_key)


def _sha(*parts: bytes) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(len(p).to_bytes(4, "big"))
        h.update(p)
    return h.hexdigest()


def _problem(
    status: int,
    title: str,
    title_id: str,
    detail: str,
    path: str,
    extra_headers: list[tuple[bytes, bytes]] | None = None,
) -> tuple[int, list, bytes]:
    body = json.dumps({"type": "about:blank", "title": title, "title_id": title_id, "status": status,
                       "detail": detail, "instance": path}).encode()
    headers = [(b"content-type", PROBLEM), (b"content-length", str(len(body)).encode())]
    if extra_headers:
        headers.extend(extra_headers)
    return status, headers, body


class IdempotencyMiddleware:
    def __init__(self, app, store: IdempotencyStore | None = None, ttl: int = DEFAULT_TTL):
        self.app, self.store, self.ttl = app, store or MemoryIdempotencyStore(), ttl

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in MUTATING:
            await self.app(scope, receive, send)
            return
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        raw_key = headers.get(b"idempotency-key")
        if raw_key is None:
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        key = raw_key.decode("latin-1")
        if not KEY_RE.fullmatch(key):
            await self._send_problem(send, _problem(422, "Invalid idempotency key", "Kunci idempotensi tidak valid",
                                                    "Use 1-128 characters: letters, digits, . _ ~ : -", path))
            return

        # Buffer the request body so it can be fingerprinted and then replayed to the app.
        chunks: list[dict] = []
        body = b""
        more = True
        while more:
            msg = await receive()
            chunks.append(msg)
            if msg["type"] == "http.request":
                body += msg.get("body", b"")
                more = msg.get("more_body", False)
            else:
                more = False
        if len(body) > MAX_BODY:
            await self.app(scope, self._replay(chunks, receive), send)
            return

        principal = _sha(headers.get(b"authorization", b""), headers.get(b"cookie", b""))
        store_key = _sha(principal.encode(), scope["method"].encode(), path.encode(), key.encode())
        fingerprint = _sha(body)

        try:
            cached = await self.store.get(store_key)
        except Exception:
            cached = None
            store_ok = False
        else:
            store_ok = True
        if cached:
            entry = json.loads(cached)
            if entry["fp"] != fingerprint:
                await self._send_problem(send, _problem(
                    422, "Idempotency key reused", "Kunci idempotensi dipakai ulang",
                    "This key was already used with a different request body.", path))
                return
            await send({"type": "http.response.start", "status": entry["status"],
                        "headers": [(k.encode(), v.encode()) for k, v in entry["headers"]]
                        + [(b"idempotent-replayed", b"true")]})
            await send({"type": "http.response.body", "body": base64.b64decode(entry["body"])})
            return

        lock_key = f"{store_key}:inflight"
        lock_value = fingerprint
        lock_acquired = False
        if store_ok and hasattr(self.store, "acquire_lock"):
            try:
                existing_lock = await self.store.acquire_lock(lock_key, lock_value, min(self.ttl, 60))  # type: ignore[attr-defined]
            except Exception:
                existing_lock = None
            else:
                lock_acquired = existing_lock is None
                if existing_lock is not None:
                    if existing_lock != fingerprint:
                        await self._send_problem(send, _problem(
                            422, "Idempotency key reused", "Kunci idempotensi dipakai ulang",
                            "This key is already being used with a different request body.", path))
                    else:
                        await self._send_problem(send, _problem(
                            409, "Idempotency request in progress", "Permintaan idempotensi sedang diproses",
                            "A request with this idempotency key is still being processed. Retry shortly.",
                            path, [(b"retry-after", b"1")]))
                    return

        captured: dict = {"start": None, "body": b"", "ok": True}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                captured["start"] = message
            elif message["type"] == "http.response.body":
                captured["body"] += message.get("body", b"")
                if len(captured["body"]) > MAX_BODY or message.get("more_body", False):
                    captured["ok"] = False  # streaming / huge responses are not cached
            await send(message)

        try:
            await self.app(scope, self._replay(chunks, receive), send_wrapper)

            start = captured["start"]
            if store_ok and captured["ok"] and start and start["status"] < 500:
                keep = {b"content-type"}
                entry = {"fp": fingerprint, "status": start["status"],
                         "headers": [[k.decode("latin-1"), v.decode("latin-1")] for k, v in start.get("headers", [])
                                     if k.lower() in keep],
                         "body": base64.b64encode(captured["body"]).decode()}
                try:
                    await self.store.put(store_key, json.dumps(entry), self.ttl)
                except Exception:
                    pass
        finally:
            if lock_acquired and hasattr(self.store, "release_lock"):
                try:
                    await self.store.release_lock(lock_key, lock_value)  # type: ignore[attr-defined]
                except Exception:
                    pass

    @staticmethod
    def _replay(chunks, receive):
        it = iter(chunks)

        async def _receive():
            try:
                return next(it)
            except StopIteration:
                return await receive()

        return _receive

    @staticmethod
    async def _send_problem(send, problem) -> None:
        status, headers, body = problem
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})
