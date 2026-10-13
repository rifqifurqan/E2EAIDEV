"""Shared-DB hygiene for tests that run against the one development Postgres."""

import asyncio

import pytest
from sqlalchemy import select


async def _restore_erased_demo_user() -> None:
    from e2eai.db import User, sessions

    async with sessions()() as session:
        for user in (await session.scalars(select(User).where(User.email.like("erased-%@erased.invalid")))).all():
            user.email, user.display_name, user.status = "andi@demo.e2eai", "Andi", "active"
        # offboarding tests disable demo users and may not re-enable them
        for user in (await session.scalars(select(User).where(User.email.like("%@demo.e2eai")))).all():
            user.status = "active"
        await session.commit()


@pytest.fixture(autouse=True)
def _restore_demo_user_after_data_subject_tests(request):
    """Data-subject erase pseudonymises the demo user Andi; later tests expect him back (order-dependence)."""
    yield
    name = request.module.__name__
    if "data_subject" in name or "dsr_" in name:
        asyncio.run(_restore_erased_demo_user())
