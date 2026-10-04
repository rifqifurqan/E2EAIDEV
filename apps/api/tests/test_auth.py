import asyncio

from e2eai.auth import (
    LOGIN_MAX_ATTEMPTS,
    Sessions,
    csrf_ok,
    hash_password,
    login_allowed,
    new_token,
    verify_password,
)


class FakeRedis:
    """Minimal async stand-in: the handful of commands the session store and rate limit use."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.expires: dict[str, int] = {}

    async def set(self, key, value, ex=None):
        self.store[key] = value
        if ex is not None:
            self.expires[key] = ex

    async def get(self, key):
        return self.store.get(key)

    async def delete(self, key):
        self.store.pop(key, None)
        self.expires.pop(key, None)

    async def expire(self, key, seconds):
        if key in self.store:
            self.expires[key] = seconds
            return True
        return False

    async def incr(self, key):
        self.store[key] = str(int(self.store.get(key, "0")) + 1)
        return int(self.store[key])


def test_password_hash_is_argon2id_and_round_trips():
    h = hash_password("correct horse")
    assert h.startswith("$argon2id$")
    assert verify_password(h, "correct horse") is True
    assert verify_password(h, "wrong") is False
    assert verify_password("not-a-hash", "whatever") is False


def test_csrf_token_compare():
    token = new_token()
    assert csrf_ok(token, token) is True
    assert csrf_ok(token, token + "x") is False
    assert csrf_ok("", "") is False  # a missing session token never validates


def test_login_rate_limit_blocks_after_max_attempts():
    redis = FakeRedis()

    async def run():
        allowed = [await login_allowed(redis, "andi@demo.e2eai") for _ in range(LOGIN_MAX_ATTEMPTS + 2)]
        return allowed

    allowed = asyncio.run(run())
    assert all(allowed[:LOGIN_MAX_ATTEMPTS]) and not any(allowed[LOGIN_MAX_ATTEMPTS:])
    assert redis.expires["login_rl:andi@demo.e2eai"] == 300  # window set once, on the first attempt


def test_session_create_get_delete_with_sliding_ttl():
    redis = FakeRedis()
    store = Sessions(redis, idle_seconds=8 * 3600)

    async def run():
        sid, csrf = await store.create("user-1")
        assert redis.expires[f"sess:{sid}"] == 8 * 3600
        redis.expires[f"sess:{sid}"] = 1  # pretend time passed
        data = await store.get(sid)
        assert data == {"user_id": "user-1", "csrf": csrf}
        assert redis.expires[f"sess:{sid}"] == 8 * 3600  # get() slid the idle window back out
        await store.delete(sid)
        return await store.get(sid)

    assert asyncio.run(run()) is None
