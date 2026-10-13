"""FR-T2/NFR-20: admin-only, cursor-paginated list of eval runs (summaries only, no item results)."""

import asyncio
import subprocess

import pytest
from sqlalchemy import delete, func, select

from e2eai.core.errors import AppError
from e2eai.db import EvalDataset, EvalRun, User, sessions
from e2eai.seed import ADMIN_EMAIL, bootstrap_admin, seed_demo


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


async def _users(session):
    await seed_demo(session, password="TestPassword_123456789")
    await bootstrap_admin(session, password="TestPassword_123456789")
    admin = await session.scalar(select(User).where(func.lower(User.email) == ADMIN_EMAIL))
    andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
    return admin, andi


def test_list_runs_page_is_admin_only_paginated_and_hides_item_results():
    from e2eai.eval_lab import list_runs_page

    async def run():
        async with sessions()() as session:
            await session.execute(delete(EvalRun))
            await session.execute(delete(EvalDataset))
            await session.commit()
            admin, andi = await _users(session)
            for i in range(3):
                session.add(EvalRun(
                    adapter="ragas.local", status="completed", metrics={"answer_correctness": 0.5 + i / 10},
                    item_results=[{"question": "secret question", "answer": "secret answer"}],
                ))
            await session.commit()

            with pytest.raises(AppError) as exc:
                await list_runs_page(session, actor=andi)
            assert exc.value.status == 403

            page1, cursor = await list_runs_page(session, actor=admin, limit=2)
            assert len(page1) == 2 and cursor
            page2, cursor2 = await list_runs_page(session, actor=admin, limit=2, cursor=cursor)
            assert len(page2) == 1 and cursor2 is None
            ids = [r["id"] for r in page1 + page2]
            assert len(set(ids)) == 3
            for item in page1 + page2:
                assert set(item) == {"id", "dataset_id", "adapter", "status", "metrics", "created_at"}
                assert "secret" not in str(item)

    _migrate()
    asyncio.run(run())
