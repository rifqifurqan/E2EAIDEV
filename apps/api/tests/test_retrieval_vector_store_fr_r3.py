"""FR-R3: retrieval through an external VectorStore keeps FR-C2 (permission filter inside the query)
and never trusts the store: hits are re-checked against the SQL permission predicate."""

import asyncio
import subprocess

import pytest
from sqlalchemy import delete, func, select

from e2eai.db import Chunk, ChunkEmbedding, DocPrincipal, Document, DocumentVersion, Folder, User, sessions
from e2eai.documents import create_seeded_document, share_document
from e2eai.seed import seed_demo
from e2eai.vector_store import InMemoryVectorStore, VectorHit, VectorQuery


class Embedder:
    model = "fake-vs-v1"

    async def embed(self, texts):
        return [[1.0, 0.0] if "leave" in t.lower() else [0.0, 1.0] for t in texts]


class RecordingAuthz:
    async def write(self, writes=(), deletes=()):
        return None


class SpyStore(InMemoryVectorStore):
    def __init__(self):
        super().__init__()
        self.queries: list[VectorQuery] = []

    async def query(self, q):
        self.queries.append(q)
        return await super().query(q)


class IgnoresFilterStore(InMemoryVectorStore):
    """A broken/malicious backend that returns every point regardless of the filter."""

    async def query(self, q):
        hits = [VectorHit(p.chunk_id, p.document_id, 0.99) for p in self._points.values()]
        return hits[: q.limit]


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


async def _reset(session):
    for model in (ChunkEmbedding, DocPrincipal, Chunk, DocumentVersion, Document, Folder):
        await session.execute(delete(model))
    await session.commit()


async def _setup(store):
    from e2eai.retrieval import index_document_chunks

    async with sessions()() as session:
        await _reset(session)
        await seed_demo(session, password="TestPassword_123456789")
        owner = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))
        andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
        shared = await create_seeded_document(session, owner=owner, title="Leave policy", text="annual leave is 12 days", page=1)
        hidden = await create_seeded_document(session, owner=owner, title="Hidden leave", text="secret leave bonus", page=1)
        emb = Embedder()
        for doc in (shared, hidden):
            await index_document_chunks(session, embedder=emb, document_id=doc.id, vector_store=store)
        await share_document(session, RecordingAuthz(), actor=owner, document_id=shared.id, principal=f"user:{andi.id}")
        return session, owner, andi, shared, hidden


def test_store_query_receives_only_permitted_document_ids_and_results_match():
    from e2eai.authz import principals
    from e2eai.retrieval import retrieve_relevant_chunks

    _migrate()

    async def run():
        store = SpyStore()
        async with sessions()() as session:
            await _reset(session)
        session, owner, andi, shared, hidden = await _setup(store)
        async with sessions()() as session:
            andi_u = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
            hits = await retrieve_relevant_chunks(
                session, embedder=Embedder(), user_principals=await principals(session, andi_u),
                question="how many leave days", limit=3, vector_store=store,
            )
            assert [h["document"] for h in hits] == ["Leave policy"]
            assert hits[0]["page"] == 1 and "text" in hits[0] and "score" in hits[0]
            sent = store.queries[-1].allowed_document_ids
            assert sent == {str(shared.id)}  # hidden doc id never reaches the backend
            assert len(store.queries[-1].vector) == 2

    asyncio.run(run())


def test_backend_that_ignores_the_filter_cannot_leak_because_hits_are_rechecked_in_sql():
    from e2eai.authz import principals
    from e2eai.retrieval import retrieve_relevant_chunks

    _migrate()

    async def run():
        store = IgnoresFilterStore()
        await _setup(store)
        async with sessions()() as session:
            andi_u = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
            hits = await retrieve_relevant_chunks(
                session, embedder=Embedder(), user_principals=await principals(session, andi_u),
                question="leave", limit=5, vector_store=store,
            )
            assert [h["document"] for h in hits] == ["Leave policy"]

    asyncio.run(run())


def test_user_without_shares_gets_nothing_and_store_is_not_queried():
    from e2eai.authz import principals
    from e2eai.retrieval import retrieve_relevant_chunks

    _migrate()

    async def run():
        store = SpyStore()
        await _setup(store)
        async with sessions()() as session:
            budi = await session.scalar(select(User).where(func.lower(User.email) == "budi@demo.e2eai"))
            store.queries.clear()
            hits = await retrieve_relevant_chunks(
                session, embedder=Embedder(), user_principals=await principals(session, budi),
                question="leave", limit=5, vector_store=store,
            )
            assert hits == [] and store.queries == []

    asyncio.run(run())


def test_hybrid_mode_with_external_store_is_rejected_clearly():
    from e2eai.core.errors import AppError
    from e2eai.retrieval import retrieve_relevant_chunks

    async def run():
        async with sessions()() as session:
            with pytest.raises(AppError) as exc:
                await retrieve_relevant_chunks(
                    session, embedder=Embedder(), user_principals=["user:x"], question="q",
                    mode="hybrid", vector_store=InMemoryVectorStore(),
                )
            assert exc.value.status == 400

    asyncio.run(run())
