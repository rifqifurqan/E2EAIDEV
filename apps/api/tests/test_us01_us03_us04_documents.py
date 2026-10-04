import asyncio
import subprocess

from sqlalchemy import delete, func, select

from e2eai.authz import principals
from e2eai.db import Chunk, DocPrincipal, Document, DocumentVersion, Folder, User, sessions
from e2eai.documents import create_seeded_document, revoke_document, share_document, visible_chunks
from e2eai.seed import seed_demo


class RecordingAuthz:
    def __init__(self):
        self.calls = []

    async def write(self, writes=(), deletes=()):
        self.calls.append({"writes": list(writes), "deletes": list(deletes)})


async def _reset_documents(session):
    for model in (DocPrincipal, Chunk, DocumentVersion, Document, Folder):
        await session.execute(delete(model))
    await session.commit()


async def _users(session):
    await seed_demo(session, password="TestPassword_123456789")
    owner = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))
    andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
    budi = await session.scalar(select(User).where(func.lower(User.email) == "budi@demo.e2eai"))
    return owner, andi, budi


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


def test_us01_us03_us04_share_retrieve_and_revoke_without_existence_leak():
    async def run():
        async with sessions()() as session:
            await _reset_documents(session)
            owner, andi, budi = await _users(session)
            doc = await create_seeded_document(
                session,
                owner=owner,
                title="WhatsApp Partnership",
                text="The WhatsApp partnership revenue share is 30 percent.",
                page=4,
            )
            authz = RecordingAuthz()
            await share_document(session, authz, actor=owner, document_id=doc.id, principal=f"user:{andi.id}")

            andi_rows = await visible_chunks(session, await principals(session, andi))
            budi_rows = await visible_chunks(session, await principals(session, budi))
            assert andi_rows == [("WhatsApp Partnership", "The WhatsApp partnership revenue share is 30 percent.", 4)]
            assert budi_rows == []  # no title/content/existence hint leaks to Budi

            assert authz.calls[0]["writes"] == [{"user": f"user:{andi.id}", "relation": "viewer", "object": f"document:{doc.id}"}]
            assert await session.get(DocPrincipal, {"document_id": doc.id, "principal": f"user:{andi.id}"}) is not None

            await revoke_document(session, authz, actor=owner, document_id=doc.id, principal=f"user:{andi.id}")
            assert await visible_chunks(session, await principals(session, andi)) == []
            assert await session.get(DocPrincipal, {"document_id": doc.id, "principal": f"user:{andi.id}"}) is None
            assert authz.calls[-1]["deletes"] == [{"user": f"user:{andi.id}", "relation": "viewer", "object": f"document:{doc.id}"}]

    _migrate()
    asyncio.run(run())
