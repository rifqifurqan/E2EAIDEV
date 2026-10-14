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
