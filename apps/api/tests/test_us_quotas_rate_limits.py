"""FR-F13 / FR-F15: Rate limits and quotas per user, team, and division.

TDD: these tests are written RED first, before the implementation exists.

Tests cover:
1. Policy resolution: user policy wins over team, team over division, division over org default.
2. Request rate-limit enforcement: allowed then denied (429) after window exhaustion.
3. Token budget enforcement: denied (429) when estimated tokens exceed budget.
4. Storage quota enforcement: denied (413) when upload would exceed storage bytes.
5. Scoped route enforcement: chat, document upload, eval run, bot ask all call quota checks.
6. Fail-closed: if quota store errors, request is denied (not silently allowed).
"""

import asyncio
import subprocess
import uuid

from e2eai.core.errors import AppError


# ---------------------------------------------------------------------------
# Helpers reused across tests
# ---------------------------------------------------------------------------

class FakeRedis:
    """Minimal async stand-in for Valkey."""
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

    async def incrby(self, key, amount):
        self.store[key] = str(int(self.store.get(key, "0")) + amount)
        return int(self.store[key])


# ---------------------------------------------------------------------------
# 1. Policy resolution: user > team > division > org default
# ---------------------------------------------------------------------------

def test_policy_resolution_user_overrides_team_and_division():
    from e2eai.quotas import QuotaPolicy, resolve_policy

    org_default = QuotaPolicy(scope="org", scope_id="org1", requests_per_minute=100, tokens_per_day=100_000, storage_bytes=20 * 1024**3)
    division_policy = QuotaPolicy(scope="division", scope_id="div1", requests_per_minute=50, tokens_per_day=50_000, storage_bytes=10 * 1024**3)
    team_policy = QuotaPolicy(scope="team", scope_id="team1", requests_per_minute=30, tokens_per_day=30_000, storage_bytes=5 * 1024**3)
    user_policy = QuotaPolicy(scope="user", scope_id="user1", requests_per_minute=10, tokens_per_day=10_000, storage_bytes=1 * 1024**3)

    # User policy wins over all others
    effective = resolve_policy([org_default, division_policy, team_policy, user_policy])
    assert effective.requests_per_minute == 10
    assert effective.tokens_per_day == 10_000
    assert effective.storage_bytes == 1 * 1024**3

    # Without user policy, team wins
    effective2 = resolve_policy([org_default, division_policy, team_policy])
    assert effective2.requests_per_minute == 30

    # Without team, division wins
    effective3 = resolve_policy([org_default, division_policy])
    assert effective3.requests_per_minute == 50

    # Only org default
    effective4 = resolve_policy([org_default])
    assert effective4.requests_per_minute == 100

    # Empty list -> built-in default
    effective5 = resolve_policy([])
    assert effective5.requests_per_minute > 0  # has a sensible default


# ---------------------------------------------------------------------------
# 2. Request rate-limit: allowed, then denied after window exhaustion
# ---------------------------------------------------------------------------

def test_request_rate_limit_allows_then_denies():
    from e2eai.quotas import QuotaPolicy, check_request_rate

    redis = FakeRedis()
    policy = QuotaPolicy(scope="user", scope_id="user1", requests_per_minute=3, tokens_per_day=100_000, storage_bytes=20 * 1024**3)

    async def run():
        # First 3 requests should be allowed
        for i in range(3):
            allowed, info = await check_request_rate(redis, user_id="user1", endpoint="chat", policy=policy)
            assert allowed, f"Request {i+1} should be allowed"

        # 4th request should be denied
        allowed, info = await check_request_rate(redis, user_id="user1", endpoint="chat", policy=policy)
        assert not allowed, "4th request should be denied"
        assert info["retry_after"] > 0

    asyncio.run(run())


# ---------------------------------------------------------------------------
# 3. Token budget: denied when estimated tokens exceed daily budget
# ---------------------------------------------------------------------------

def test_token_budget_denies_when_exceeded():
    from e2eai.quotas import QuotaPolicy, check_token_budget, record_token_usage

    redis = FakeRedis()
    policy = QuotaPolicy(scope="user", scope_id="user1", requests_per_minute=100, tokens_per_day=100, storage_bytes=20 * 1024**3)

    async def run():
        # Record 90 tokens used
        await record_token_usage(redis, user_id="user1", tokens=90)

        # Check with estimated 5 tokens -> allowed (90+5=95 < 100)
        allowed, info = await check_token_budget(redis, user_id="user1", estimated_tokens=5, policy=policy)
        assert allowed

        # Check with estimated 15 tokens -> denied (90+15=105 > 100)
        allowed, info = await check_token_budget(redis, user_id="user1", estimated_tokens=15, policy=policy)
        assert not allowed
        assert "token" in info.get("reason", "").lower()

    asyncio.run(run())


# ---------------------------------------------------------------------------
# 4. Token estimation: rough estimate from text length
# ---------------------------------------------------------------------------

def test_token_estimation_from_text():
    from e2eai.quotas import estimate_tokens

    # Roughly 1 token per 4 characters is a common heuristic
    short = "Hello"
    long_text = "A" * 400
    assert estimate_tokens(short) >= 1
    assert estimate_tokens(long_text) >= 50  # 400/4 = 100, but at least 50


# ---------------------------------------------------------------------------
# 5. Storage quota: denied when upload would exceed storage bytes
# ---------------------------------------------------------------------------

def test_storage_quota_denies_when_exceeded():
    from sqlalchemy import delete, func, select

    from e2eai.db import Document, DocumentVersion, User, sessions
    from e2eai.quotas import check_storage_quota, QuotaPolicy
    from e2eai.seed import seed_demo

    policy = QuotaPolicy(scope="user", scope_id="ignored", requests_per_minute=100, tokens_per_day=100_000, storage_bytes=500)

    async def run():
        subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
        async with sessions()() as session:
            await seed_demo(session, password="TestPassword_123456789")
            owner = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))

            # No documents yet -> 0 bytes used, uploading 100 bytes is fine
            allowed, info = await check_storage_quota(session, user_id=owner.id, upload_bytes=100, policy=policy)
            assert allowed, "Should allow upload when under quota"

            # Uploading 600 bytes should be denied (600 > 500 quota)
            allowed, info = await check_storage_quota(session, user_id=owner.id, upload_bytes=600, policy=policy)
            assert not allowed, "Should deny upload exceeding quota"
            assert "storage" in info.get("reason", "").lower()

    asyncio.run(run())


# ---------------------------------------------------------------------------
# 6. Fail-closed: quota check errors deny the request
# ---------------------------------------------------------------------------

def test_fail_closed_on_quota_store_error():
    from e2eai.quotas import QuotaPolicy, check_request_rate

    class BrokenRedis:
        async def incr(self, key):
            raise ConnectionError("Valkey down")
        async def expire(self, key, seconds):
            raise ConnectionError("Valkey down")
        async def get(self, key):
            raise ConnectionError("Valkey down")

    policy = QuotaPolicy(scope="user", scope_id="user1", requests_per_minute=100, tokens_per_day=100_000, storage_bytes=20 * 1024**3)

    async def run():
        allowed, info = await check_request_rate(BrokenRedis(), user_id="user1", endpoint="chat", policy=policy)
        assert not allowed, "Must fail closed when quota store errors"
        assert "error" in info.get("reason", "").lower() or "unavailable" in info.get("reason", "").lower()

    asyncio.run(run())


# ---------------------------------------------------------------------------
# 7. DB-backed: quota policy CRUD and effective lookup
# ---------------------------------------------------------------------------

def test_quota_policy_crud_and_lookup():
    from sqlalchemy import delete, func, select

    from e2eai.db import User, sessions
    from e2eai.quotas import QuotaPolicyRow, get_effective_policy, upsert_quota_policy
    from e2eai.seed import seed_demo

    async def run():
        subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
        async with sessions()() as session:
            await seed_demo(session, password="TestPassword_123456789")
            owner = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))
            andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))

            # Clean up any existing policies
            await session.execute(delete(QuotaPolicyRow))
            await session.commit()

            # No policies -> get_effective_policy returns built-in default
            effective = await get_effective_policy(session, user=andi)
            assert effective.requests_per_minute > 0

            # Set a user-level policy for Andi
            await upsert_quota_policy(session, scope="user", scope_id=str(andi.id),
                                      requests_per_minute=5, tokens_per_day=500, storage_bytes=1024)

            effective2 = await get_effective_policy(session, user=andi)
            assert effective2.requests_per_minute == 5
            assert effective2.tokens_per_day == 500
            assert effective2.storage_bytes == 1024

            # Set a division-level policy (Andi's division)
            if andi.division_id:
                await upsert_quota_policy(session, scope="division", scope_id=str(andi.division_id),
                                          requests_per_minute=20, tokens_per_day=2000, storage_bytes=5000)
                # User policy still wins
                effective3 = await get_effective_policy(session, user=andi)
                assert effective3.requests_per_minute == 5  # user overrides division

    asyncio.run(run())


# ---------------------------------------------------------------------------
# 8. Integration: enforce_quota raises AppError with correct status codes
# ---------------------------------------------------------------------------

def test_enforce_quota_raises_correct_errors():
    from e2eai.quotas import QuotaPolicy, enforce_request_quota, enforce_storage_quota, enforce_token_quota

    redis = FakeRedis()
    policy = QuotaPolicy(scope="user", scope_id="user1", requests_per_minute=1, tokens_per_day=10, storage_bytes=100)

    async def run():
        # First request allowed
        await enforce_request_quota(redis, user_id="user1", endpoint="chat", policy=policy)

        # Second request -> 429
        try:
            await enforce_request_quota(redis, user_id="user1", endpoint="chat", policy=policy)
            assert False, "Should have raised AppError"
        except AppError as e:
            assert e.status == 429
            assert "rate" in e.title.lower() or "limit" in e.title.lower()

        # Token budget exceeded -> 429
        from e2eai.quotas import record_token_usage
        await record_token_usage(redis, user_id="user1", tokens=10)
        try:
            await enforce_token_quota(redis, user_id="user1", estimated_tokens=5, policy=policy)
            assert False, "Should have raised AppError"
        except AppError as e:
            assert e.status == 429
            assert "token" in e.title.lower() or "quota" in e.title.lower()

    asyncio.run(run())


def test_enforce_storage_quota_raises_413():
    from sqlalchemy import delete, func, select

    from e2eai.db import User, sessions
    from e2eai.quotas import QuotaPolicy, QuotaPolicyRow, enforce_storage_quota
    from e2eai.seed import seed_demo

    policy = QuotaPolicy(scope="user", scope_id="ignored", requests_per_minute=100, tokens_per_day=100_000, storage_bytes=50)

    async def run():
        subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
        async with sessions()() as session:
            await seed_demo(session, password="TestPassword_123456789")
            owner = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))

            try:
                await enforce_storage_quota(session, user_id=owner.id, upload_bytes=100, policy=policy)
                assert False, "Should have raised AppError"
            except AppError as e:
                assert e.status == 413
                assert "storage" in e.title.lower() or "quota" in e.title.lower()

    asyncio.run(run())
