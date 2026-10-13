"""FR-I1 / NFR-20: flywheel summary counts must cover the whole queue, not just the first 1000 rows."""

import asyncio
import subprocess

from sqlalchemy import delete, func, select

from e2eai.db import AuditEntry, FlywheelItem, User, sessions
from e2eai.seed import ADMIN_EMAIL, bootstrap_admin, seed_demo


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


def test_summary_counts_cover_more_than_1000_rows_and_status_filter_applies_in_sql():
    async def run():
        from e2eai.flywheel import queue_summary

        async with sessions()() as session:
            await session.execute(delete(AuditEntry).where(AuditEntry.action.like("flywheel.%")))
            await session.execute(delete(FlywheelItem))
            await session.commit()
            await seed_demo(session, password="TestPassword_123456789")
            await bootstrap_admin(session, password="TestPassword_123456789")
            admin = await session.scalar(select(User).where(func.lower(User.email) == ADMIN_EMAIL))
            session.add_all(
                [FlywheelItem(source="reviewer_flag", status="queued", question_masked=f"Q{n}") for n in range(1003)]
                + [FlywheelItem(source="thumbs_down", status="dismissed", question_masked=f"D{n}") for n in range(3)]
            )
            await session.commit()

            out = await queue_summary(session, actor=admin)
            assert out["by_status"] == {"dismissed": 3, "queued": 1003}
            assert out["by_source"] == {"reviewer_flag": 1003, "thumbs_down": 3}
            assert len(out["items"]) == 200

            only = await queue_summary(session, actor=admin, status="dismissed")
            assert len(only["items"]) == 3 and all(i["status"] == "dismissed" for i in only["items"])
            assert only["by_status"] == {"dismissed": 3, "queued": 1003}  # counts stay global

            await session.execute(delete(FlywheelItem))
            await session.commit()

    _migrate()
    asyncio.run(run())
