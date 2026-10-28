"""A version is 'ready' only when it can be searched: parsing alone is not enough (FR-D3, FR-F20).

Before this, `ready` was committed before the embeddings were created, so a user who saw 'ready' and asked at once
got "no relevant documents" for a few seconds (found in the live PDF check)."""

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from e2eai.core.errors import AppError
from e2eai.db import DocumentVersion, User, sessions
from e2eai.documents import create_uploaded_document
from e2eai.ingest import ingest_version
from e2eai.seed import seed_demo


class _Memory:
    def __init__(self):
        self.blobs = {}

    async def put_bytes(self, data: bytes):
        key = f"sha256/{len(self.blobs)}"
        self.blobs[key] = data
        return key, key

    async def get_bytes(self, key: str) -> bytes:
        return self.blobs[key]


class _Clean:
    async def scan(self, data: bytes):
        return SimpleNamespace(verdict="clean", signature=None)


async def _upload(session, storage):
    await seed_demo(session, password="TestPassword_123456789")
    andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
    doc = await create_uploaded_document(session, owner=andi, title="policy.md", data=b"# Leave\nTwelve days of leave.",
                                         mime="text/markdown", storage=storage)
    await session.commit()
    return doc


async def _status(version_id: uuid.UUID) -> str:
    async with sessions()() as other:  # a separate session sees only what is committed, like another user would
        return (await other.get(DocumentVersion, version_id)).parse_status


def test_a_version_is_indexing_while_embeddings_are_made_and_ready_only_afterwards():
    seen = {}

    async def run():
        storage = _Memory()
        async with sessions()() as session:
            doc = await _upload(session, storage)
            vid = doc.current_version_id

            class _Embedder:
                model = "fake-v1"

                async def embed(self, texts):
                    seen["during"] = await _status(vid)
                    return [[1.0, 0.0] for _ in texts]

            result = await ingest_version(session, embedder=_Embedder(), version_id=vid, storage=storage, scanner=_Clean())
            seen["after"] = await _status(vid)
            seen["result"] = result["status"]

    asyncio.run(run())
    assert seen == {"during": "indexing", "after": "ready", "result": "ready"}


def test_an_embedding_failure_never_leaves_a_version_marked_ready():
    async def run():
        storage = _Memory()
        async with sessions()() as session:
            doc = await _upload(session, storage)
            vid = doc.current_version_id

            class _Down:
                model = "fake-v1"

                async def embed(self, texts):
                    raise AppError(503, "Embedding service unavailable")

            with pytest.raises(AppError):
                await ingest_version(session, embedder=_Down(), version_id=vid, storage=storage, scanner=_Clean())
            return await _status(vid)

    assert asyncio.run(run()) == "indexing"  # honest: parsed, not yet searchable; a retry (or the failure marker) finishes it


def test_the_failure_marker_also_closes_a_version_stuck_while_indexing():
    async def run():
        from e2eai.jobs.ingest import mark_ingest_failed

        storage = _Memory()
        async with sessions()() as session:
            doc = await _upload(session, storage)
            vid = doc.current_version_id
            version = await session.get(DocumentVersion, vid)
            version.parse_status = "indexing"
            await session.commit()
        await mark_ingest_failed(vid, "ConnectionError")
        return await _status(vid)

    assert asyncio.run(run()) == "failed"
