"""FR-R3: `components.vector_store` decides which store the ingest, purge and retrieval paths use."""

import asyncio
import dataclasses
import subprocess
import uuid

import pytest
from sqlalchemy import delete, func, select

from e2eai import vector_store as vs
from e2eai.core.config import get_settings
from e2eai.db import Chunk, ChunkEmbedding, DocPrincipal, Document, DocumentVersion, Folder, User, sessions
from e2eai.documents import create_seeded_document, share_document
from e2eai.seed import seed_demo
from e2eai.vector_store import InMemoryVectorStore, QdrantVectorStore, VectorPoint, VectorQuery


def with_store(name, **kw):
    return dataclasses.replace(get_settings(), vector_store=name, **kw)


def test_pgvector_means_no_external_store():
    assert vs.configured_vector_store(with_store("pgvector")) is None


def test_qdrant_setting_builds_adapter_without_leaking_key_in_repr_and_is_cached():
    s = with_store("qdrant", qdrant_url="http://127.0.0.1:16333", qdrant_api_key="k" * 20)
    a = vs.configured_vector_store(s)
    b = vs.configured_vector_store(s)
    assert isinstance(a, QdrantVectorStore) and a is b
    assert "k" * 20 not in repr(a)


def test_collection_dimension_is_taken_from_the_first_upserted_vector():
    created = []

    class Rec(QdrantVectorStore):
        async def _call(self, method, path, body):
            if method == "PUT" and path.count("/") == 2:
                created.append(body["vectors"]["size"])
            return {"result": []}

    store = Rec(base_url="http://q", api_key="", collection="c", dims=0)
    asyncio.run(store.upsert([VectorPoint(str(uuid.uuid4()), "d", [0.1, 0.2, 0.3])]))
    assert created == [3]


class Embedder:
    model = "fake-conf-v1"

    async def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


class Authz:
    async def write(self, writes=(), deletes=()):
        return None


class Spy(InMemoryVectorStore):
    def __init__(self):
        super().__init__()
        self.queries = 0

    async def query(self, q):
        self.queries += 1
        return await super().query(q)


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


def test_retrieval_uses_the_configured_store_for_dense_and_sql_for_hybrid(monkeypatch):
    from e2eai.authz import principals
    from e2eai.retrieval import index_document_chunks, retrieve_relevant_chunks

    _migrate()
    spy = Spy()
    monkeypatch.setattr(vs, "configured_vector_store", lambda settings=None: spy)

    async def run():
        async with sessions()() as session:
            for model in (ChunkEmbedding, DocPrincipal, Chunk, DocumentVersion, Document, Folder):
                await session.execute(delete(model))
            await session.commit()
            await seed_demo(session, password="TestPassword_123456789")
            owner = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))
            andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
            doc = await create_seeded_document(session, owner=owner, title="Leave", text="leave is 12 days", page=1)
            await index_document_chunks(session, embedder=Embedder(), document_id=doc.id)
            assert len(spy._points) == 1  # indexing used the configured store without an explicit argument
            await share_document(session, Authz(), actor=owner, document_id=doc.id, principal=f"user:{andi.id}")
            p = await principals(session, andi)
            dense = await retrieve_relevant_chunks(session, embedder=Embedder(), user_principals=p, question="leave")
            assert [h["document"] for h in dense] == ["Leave"] and spy.queries == 1
            hybrid = await retrieve_relevant_chunks(session, embedder=Embedder(), user_principals=p,
                                                    question="leave", mode="hybrid")
            assert [h["document"] for h in hybrid] == ["Leave"] and spy.queries == 1  # hybrid stays on SQL

    asyncio.run(run())
