"""Shared-DB hygiene for tests that run against the one development Postgres.

FR-RL3: when E2EAI_SKIP_DB_TESTS is set (hosted CI has no Postgres/OpenFGA/.env), any test
that reaches the DB is skipped instead of erroring, while the pure deterministic logic
(eval metrics, red-team scoring, release-gate policy) still runs and gates on regression.
Unset (local full-stack runs), behaviour is unchanged.
"""

import asyncio
import os

import pytest
from sqlalchemy import func, select

if os.environ.get("E2EAI_SKIP_DB_TESTS"):
    import e2eai.db as _db

    def _skip_db(*_args, **_kwargs):
        pytest.skip("DB-backed test skipped: E2EAI_SKIP_DB_TESTS set (no live stack)")

    _db.engine.cache_clear()
    _db.sessions.cache_clear()
    _db.engine = _skip_db
    _db.sessions = _skip_db

    # Some suites bootstrap the DB themselves (alembic via subprocess, or settings that need
    # deploy/compose/.env). Without a live stack that is "environment missing", not a regression.
    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(item, call):
        outcome = yield
        report = outcome.get_result()
        if report.when != "call" or not report.failed or call.excinfo is None:
            return
        exc = call.excinfo.value
        text = f"{type(exc).__name__}: {exc}"
        no_stack = "run the wizard first" in text or (
            type(exc).__name__ == "CalledProcessError" and "alembic" in str(getattr(exc, "cmd", ""))
        )
        if no_stack:
            report.outcome = "skipped"
            report.longrepr = (str(item.path), item.location[1] or 0, "Skipped: no live stack (E2EAI_SKIP_DB_TESTS)")


async def _truncate_dedicated_test_state() -> None:
    """Empty every table (except alembic_version) and the Valkey database of a DEDICATED test install."""
    from redis.asyncio import Redis
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from e2eai.core.config import get_settings

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.begin() as conn:
            names = (await conn.execute(text(
                "select tablename from pg_tables where schemaname = 'public' and tablename <> 'alembic_version'"))).scalars().all()
            if names:
                await conn.execute(text("TRUNCATE " + ", ".join(f'"{n}"' for n in names) + " RESTART IDENTITY CASCADE"))
    finally:
        await engine.dispose()
    redis = Redis.from_url(settings.valkey_url)
    try:
        await redis.flushdb()  # sessions / rate-limit counters of the test database only (never database 0)
    finally:
        await redis.aclose()


@pytest.fixture(scope="module", autouse=True)
def _every_module_starts_from_an_empty_test_install():
    """Order independence: many tests wipe tables themselves and assume nobody left rows behind (e.g. message_citations
    from an earlier module). On a dedicated `*_test` database each module starts empty. The development database
    (`e2eai`, Valkey database 0) is never touched: run the suite with
    E2EAI_DB_NAME=e2eai_test E2EAI_VALKEY_DB=1 E2EAI_OPENFGA_STORE=e2eai-test (see AGENTS.md)."""
    if os.environ.get("E2EAI_SKIP_DB_TESTS"):
        yield
        return
    from e2eai.core.config import get_settings

    url = get_settings().database_url
    if url.rsplit("/", 1)[-1].endswith("_test") and not get_settings().valkey_url.endswith("/0"):
        asyncio.run(_truncate_dedicated_test_state())
    yield


async def _restore_erased_demo_user() -> None:
    from e2eai.db import User, sessions

    async with sessions()() as session:
        andi_exists = await session.scalar(select(User.id).where(func.lower(User.email) == "andi@demo.e2eai"))
        if andi_exists is None:  # a stale erased row must not be renamed onto an existing Andi (unique email)
            for user in (await session.scalars(select(User).where(User.email.like("erased-%@erased.invalid")).limit(1))).all():
                user.email, user.display_name, user.status = "andi@demo.e2eai", "Andi", "active"
        # offboarding tests disable demo users and may not re-enable them
        for user in (await session.scalars(select(User).where(User.email.like("%@demo.e2eai")))).all():
            user.status = "active"
        await session.commit()


@pytest.fixture(autouse=True)
def _restore_demo_user_after_data_subject_tests(request):
    """Data-subject erase pseudonymises the demo user Andi; later tests expect him back (order-dependence)."""
    yield
    if os.environ.get("E2EAI_SKIP_DB_TESTS"):
        return
    name = request.module.__name__
    if "data_subject" in name or "dsr_" in name:
        asyncio.run(_restore_erased_demo_user())
