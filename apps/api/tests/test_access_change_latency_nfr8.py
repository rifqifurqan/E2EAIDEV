"""NFR-8: access changes apply in <= 5 s (here: on the very next permission check, measured)."""
import asyncio
import subprocess
import time

from sqlalchemy import delete, func, select

from e2eai.authz import principals
from e2eai.db import Chunk, ChunkEmbedding, DocPrincipal, Document, DocumentVersion, Folder, User, sessions
from e2eai.documents import create_seeded_document, revoke_document, share_document, visible_chunks
from e2eai.org import add_team_member, create_team, remove_team_member
from e2eai.seed import seed_demo

ACCESS_CHANGE_BUDGET_SECONDS = 5.0


class RecordingAuthz:
    def __init__(self):
        self.calls = []

    async def write(self, writes=(), deletes=()):
        self.calls.append({"writes": list(writes), "deletes": list(deletes)})


async def _reset(session):
    for model in (ChunkEmbedding, DocPrincipal, Chunk, DocumentVersion, Document, Folder):
        await session.execute(delete(model))
    await session.commit()


async def _user(session, email):
    return await session.scalar(select(User).where(func.lower(User.email) == email))


def test_team_membership_removal_hides_document_within_budget():
    async def run():
        async with sessions()() as session:
            await _reset(session)
            await seed_demo(session, password="TestPassword_123456789")
            owner = await _user(session, "intern@demo.e2eai")
            andi = await _user(session, "andi@demo.e2eai")
            team = await create_team(session, division_id=andi.division_id, name="NFR8 latency team", actor="test")
            await add_team_member(session, team_id=team.id, user_id=andi.id, actor="test")
            await session.commit()

            doc = await create_seeded_document(session, owner=owner, title="Team doc", text="Team only text.", page=1)
            await share_document(session, RecordingAuthz(), actor=owner, document_id=doc.id, principal=f"team:{team.id}")

            assert len(await visible_chunks(session, await principals(session, andi))) == 1

            started = time.monotonic()
            await remove_team_member(session, team_id=team.id, user_id=andi.id, actor="test")
            await session.commit()
            rows = await visible_chunks(session, await principals(session, andi))
            elapsed = time.monotonic() - started

            assert rows == []
            assert elapsed <= ACCESS_CHANGE_BUDGET_SECONDS

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
    asyncio.run(run())


def test_document_revoke_hides_document_within_budget_and_tightens_before_openfga():
    async def run():
        async with sessions()() as session:
            await _reset(session)
            await seed_demo(session, password="TestPassword_123456789")
            owner = await _user(session, "intern@demo.e2eai")
            andi = await _user(session, "andi@demo.e2eai")
            doc = await create_seeded_document(session, owner=owner, title="Direct doc", text="Direct text.", page=1)
            authz = RecordingAuthz()
            await share_document(session, authz, actor=owner, document_id=doc.id, principal=f"user:{andi.id}")
            assert len(await visible_chunks(session, await principals(session, andi))) == 1

            started = time.monotonic()
            await revoke_document(session, authz, actor=owner, document_id=doc.id, principal=f"user:{andi.id}")
            rows = await visible_chunks(session, await principals(session, andi))
            elapsed = time.monotonic() - started

            assert rows == []
            assert elapsed <= ACCESS_CHANGE_BUDGET_SECONDS

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
    asyncio.run(run())


def test_deactivated_user_loses_all_principals_immediately():
    async def run():
        async with sessions()() as session:
            await seed_demo(session, password="TestPassword_123456789")
            andi = await _user(session, "andi@demo.e2eai")
            assert await principals(session, andi)
            andi.status = "disabled"
            try:
                assert await principals(session, andi) == set()
            finally:
                await session.rollback()

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
    asyncio.run(run())
