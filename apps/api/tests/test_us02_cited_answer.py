import asyncio
import subprocess

from sqlalchemy import delete, func, select

from e2eai.authz import principals
from e2eai.db import Chunk, ChunkEmbedding, DocPrincipal, Document, DocumentVersion, Folder, User, sessions
from e2eai.documents import create_seeded_document, share_document
from e2eai.retrieval import answer_question, index_document_chunks
from e2eai.seed import seed_demo


class RecordingAuthz:
    async def write(self, writes=(), deletes=()):
        return None


class FakeEmbedder:
    model = "fake-embedding-v1"

    async def embed(self, texts):
        return [[float(len(text)), float(text.lower().count("revenue"))] for text in texts]


async def _reset_documents(session):
    for model in (ChunkEmbedding, DocPrincipal, Chunk, DocumentVersion, Document, Folder):
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


def test_us02_answer_has_page_citation_and_us03_unshared_user_gets_no_leak():
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
            await share_document(session, RecordingAuthz(), actor=owner, document_id=doc.id, principal=f"user:{andi.id}")
            await index_document_chunks(session, embedder=FakeEmbedder(), document_id=doc.id)

            embedding_count = await session.scalar(select(func.count()).select_from(ChunkEmbedding))
            assert embedding_count == 1

            andi_answer = await answer_question(session, user=andi, question="What's the revenue share in the WhatsApp partnership?")
            assert "30 percent" in andi_answer["answer"]
            assert andi_answer["citations"] == [
                {"document": "WhatsApp Partnership", "page": 4, "section": "seed"}
            ]

            budi_answer = await answer_question(session, user=budi, question="What's the revenue share in the WhatsApp partnership?")
            assert budi_answer["citations"] == []
            assert "WhatsApp" not in budi_answer["answer"]
            assert "30 percent" not in budi_answer["answer"]

    _migrate()
    asyncio.run(run())
