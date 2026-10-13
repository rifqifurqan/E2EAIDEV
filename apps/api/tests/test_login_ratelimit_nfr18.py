"""NFR-18: login rate limiting per account AND per client address, with Retry-After on the 429."""

import asyncio

from e2eai.auth import LOGIN_IP_MAX_ATTEMPTS, LOGIN_MAX_ATTEMPTS, login_decision


class FakeRedis:
    def __init__(self):
        self.store: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    async def incr(self, key):
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    async def expire(self, key, seconds):
        self.ttls[key] = seconds
        return True

    async def ttl(self, key):
        return self.ttls.get(key, -1)


def _decide(r, email, ip):
    return asyncio.run(login_decision(r, email, ip))


def test_one_address_trying_many_accounts_is_blocked_by_the_ip_limit():
    r = FakeRedis()
    results = [_decide(r, f"user{i}@demo.e2eai", "203.0.113.9") for i in range(LOGIN_IP_MAX_ATTEMPTS + 3)]
    assert all(a for a, _ in results[:LOGIN_IP_MAX_ATTEMPTS])
    assert not any(a for a, _ in results[LOGIN_IP_MAX_ATTEMPTS:])
    assert LOGIN_IP_MAX_ATTEMPTS > LOGIN_MAX_ATTEMPTS  # an office NAT must outlast a single account's limit


def test_one_account_attacked_from_many_addresses_is_blocked_by_the_account_limit():
    r = FakeRedis()
    results = [_decide(r, "andi@demo.e2eai", f"198.51.100.{i}") for i in range(LOGIN_MAX_ATTEMPTS + 2)]
    assert all(a for a, _ in results[:LOGIN_MAX_ATTEMPTS])
    assert not any(a for a, _ in results[LOGIN_MAX_ATTEMPTS:])


def test_blocked_decision_carries_a_positive_retry_after():
    r = FakeRedis()
    for _ in range(LOGIN_MAX_ATTEMPTS):
        _decide(r, "andi@demo.e2eai", "192.0.2.1")
    allowed, retry_after = _decide(r, "andi@demo.e2eai", "192.0.2.1")
    assert allowed is False and 0 < retry_after <= 300


def test_email_is_case_insensitive_and_keys_do_not_store_raw_address_or_email():
    r = FakeRedis()
    _decide(r, "Andi@Demo.E2EAI", "192.0.2.1")
    _decide(r, "andi@demo.e2eai", "192.0.2.1")
    assert any(v == 2 for v in r.store.values())
    joined = " ".join(r.store)
    assert "andi" not in joined and "192.0.2.1" not in joined


def test_missing_ttl_still_gives_a_safe_retry_after():
    class NoTtl(FakeRedis):
        async def ttl(self, key):
            return -1

    r = NoTtl()
    for _ in range(LOGIN_MAX_ATTEMPTS):
        _decide(r, "a@b.c", "192.0.2.1")
    allowed, retry_after = _decide(r, "a@b.c", "192.0.2.1")
    assert allowed is False and retry_after >= 1


def test_login_endpoint_returns_429_problem_with_retry_after(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import e2eai.auth as auth
    from e2eai.core.errors import install
    from e2eai.db import get_session

    fake = FakeRedis()
    monkeypatch.setattr(auth, "redis_client", lambda: fake)
    app = FastAPI()
    install(app)
    app.include_router(auth.router)

    async def no_db():
        yield None

    app.dependency_overrides[get_session] = no_db
    c = TestClient(app, raise_server_exceptions=False)
    for _ in range(LOGIN_MAX_ATTEMPTS):
        asyncio.run(login_decision(fake, "andi@demo.e2eai", "testclient"))
    r = c.post("/api/v1/auth/login", json={"email": "andi@demo.e2eai", "password": "x"})
    assert r.status_code == 429
    assert r.headers["content-type"].startswith("application/problem+json")
    assert 0 < int(r.headers["retry-after"]) <= 300
