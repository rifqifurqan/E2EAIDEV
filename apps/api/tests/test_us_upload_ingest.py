"""Phase 1 parser/ingest slice (FR-D1, FR-D3, FR-D4): upload -> parse stored object ->
structure-aware chunks -> embed -> cited answer, with no leak for an unshared user.

Parser unit tests run offline (no DB). The ingest integration tests use a fake embedder and the
real pgvector retrieval path, so they prove permission filtering happens before scoring.
"""

import asyncio
import subprocess

import pytest
from sqlalchemy import delete, func, select

from e2eai.authz import principals
from e2eai.core.errors import AppError
from e2eai.db import Chunk, ChunkEmbedding, DocPrincipal, Document, DocumentVersion, Folder, User, sessions
from e2eai.documents import LocalObjectStorage, S3ObjectStorage, create_uploaded_document, share_document
from e2eai.ingest import DoclingParser, TextMarkdownParser, ingest_version, select_parser
from e2eai.retrieval import answer_question
from e2eai.seed import seed_demo

REVENUE = "The WhatsApp partnership revenue share is 30 percent."
HOLIDAY = "The office holiday schedule is posted on the board."
MARKDOWN = f"# WhatsApp Partnership\n\n## Revenue\n{REVENUE}\n\n## Holidays\n{HOLIDAY}\n".encode()


class RecordingAuthz:
    async def write(self, writes=(), deletes=()):
        return None


class FakeEmbedder:
    """Keyword one-hot embedder: retrieval must rank by vector distance, not keyword/title overlap."""

    model = "fake-embedding-v1"
    _axes = ("revenue", "holiday")

    async def embed(self, texts):
        return [[float(t.lower().count(a)) for a in self._axes] for t in texts]


class FakeS3Body:
    def __init__(self, data: bytes):
        self.data = data

    async def read(self) -> bytes:
        return self.data


class FakeS3Client:
    def __init__(self):
        self.objects = {}
        self.put_calls = []
        self.delete_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def put_object(self, **kwargs):
        self.put_calls.append(kwargs)
        self.objects[(kwargs["Bucket"], kwargs["Key"])] = kwargs["Body"]

    async def get_object(self, **kwargs):
        return {"Body": FakeS3Body(self.objects[(kwargs["Bucket"], kwargs["Key"])])}

    async def delete_object(self, **kwargs):
        self.delete_calls.append(kwargs)
        self.objects.pop((kwargs["Bucket"], kwargs["Key"]), None)


class FakeS3Session:
    def __init__(self, client: FakeS3Client):
        self.client_instance = client
        self.client_calls = []

    def client(self, *args, **kwargs):
        self.client_calls.append((args, kwargs))
        return self.client_instance


def test_s3_storage_uses_seaweedfs_compatible_bucket_and_content_addressed_keys():
    async def run():
        client = FakeS3Client()
        session = FakeS3Session(client)
        storage = S3ObjectStorage(
            endpoint_url="http://127.0.0.1:18333",
            bucket="e2eai",
            access_key="access-id",
            secret_key="secret-value",
            session_factory=lambda: session,
        )
        key, digest = await storage.put_bytes(b"hello")

        assert key == f"sha256/{digest}"
        assert client.objects[("e2eai", key)] == b"hello"
        assert session.client_calls[0] == (
            ("s3",),
            {
                "endpoint_url": "http://127.0.0.1:18333",
                "aws_access_key_id": "access-id",
                "aws_secret_access_key": "secret-value",
                "region_name": "us-east-1",
            },
        )
        assert await storage.get_bytes(key) == b"hello"
        await storage.delete(key)
        assert client.delete_calls == [{"Bucket": "e2eai", "Key": key}]
        assert ("e2eai", key) not in client.objects

    asyncio.run(run())


def test_text_markdown_parser_splits_by_heading_into_section_paths():
    chunks = TextMarkdownParser().parse(MARKDOWN, mime="text/markdown")
    sections = {c.section_path: c.text for c in chunks}
    assert any("Revenue" in s and REVENUE in t for s, t in sections.items())
    assert any("Holidays" in s and HOLIDAY in t for s, t in sections.items())
    assert all(c.page == 1 for c in chunks)
    assert len(chunks) == 2  # the heading-only title line has no body and is not a chunk


def test_text_parser_yields_one_chunk_for_plain_text_without_headings():
    chunks = TextMarkdownParser().parse(b"Internal leave policy: 12 days.", mime="text/plain")
    assert len(chunks) == 1
    assert chunks[0].section_path == ""
    assert chunks[0].text == "Internal leave policy: 12 days."
    assert chunks[0].page == 1


def test_text_parser_counts_form_feed_pages():
    chunks = TextMarkdownParser().parse(b"page one text\n\x0cpage two text", mime="text/plain")
    assert [c.page for c in chunks] == [1]  # one section, started on page 1
    assert "page two text" in chunks[0].text


def test_select_parser_routes_text_to_markdown_and_binary_to_docling():
    assert isinstance(select_parser("text/markdown"), TextMarkdownParser)
    assert isinstance(select_parser("text/plain"), TextMarkdownParser)
    assert isinstance(select_parser("application/pdf"), DoclingParser)


def test_docling_parser_raises_clear_apperror_when_unavailable():
    try:
        import docling  # noqa: F401
    except ImportError:
        with pytest.raises(AppError) as ei:
            DoclingParser().parse(b"%PDF-1.4 fake", mime="application/pdf")
        assert ei.value.status == 503
    else:
        pytest.skip("docling installed; the offline stub path is not exercised here")


async def _reset(session):
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


def test_upload_markdown_ingest_chunks_cited_answer_and_no_leak(tmp_path):
    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi, budi = await _users(session)
            storage = LocalObjectStorage(tmp_path / "objects")

            doc = await create_uploaded_document(
                session, owner=owner, title="deal.md", data=MARKDOWN, mime="text/markdown", storage=storage
            )
            version = await session.get(DocumentVersion, doc.current_version_id)
            assert version.parse_status == "pending"  # upload stores the object; ingest parses it
            assert await session.scalar(select(func.count()).select_from(Chunk)) == 0

            result = await ingest_version(
                session, embedder=FakeEmbedder(), version_id=doc.current_version_id, storage=storage
            )
            assert result["status"] == "ready"
            assert result["chunks"] == 2
            await session.refresh(version)
            assert version.parse_status == "ready"
            assert await session.scalar(select(func.count()).select_from(ChunkEmbedding)) == 2

            await share_document(session, RecordingAuthz(), actor=owner, document_id=doc.id, principal=f"user:{andi.id}")

            andi_answer = await answer_question(
                session, embedder=FakeEmbedder(), user=andi,
                question="What is the revenue share in the WhatsApp partnership?",
            )
            assert "30 percent" in andi_answer["answer"]
            assert "Revenue" in andi_answer["citations"][0]["section"]

            budi_answer = await answer_question(
                session, embedder=FakeEmbedder(), user=budi,
                question="What is the revenue share in the WhatsApp partnership?",
            )
            assert budi_answer["citations"] == []
            assert "WhatsApp" not in budi_answer["answer"]
            assert "30 percent" not in budi_answer["answer"]

    _migrate()
    asyncio.run(run())


def test_ingest_unparseable_binary_sets_failed_without_chunks_or_leak(tmp_path):
    try:
        import docling  # noqa: F401
    except ImportError:
        pass
    else:
        pytest.skip("docling installed; the offline failed-parse path is not exercised here")

    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, _andi, _budi = await _users(session)
            storage = LocalObjectStorage(tmp_path / "objects")
            doc = await create_uploaded_document(
                session, owner=owner, title="scan.pdf", data=b"%PDF-1.4 fake", mime="application/pdf", storage=storage
            )
            result = await ingest_version(
                session, embedder=FakeEmbedder(), version_id=doc.current_version_id, storage=storage
            )
            assert result["status"] == "failed"
            assert result["chunks"] == 0
            version = await session.get(DocumentVersion, doc.current_version_id)
            assert version.parse_status == "failed"
            assert await session.scalar(select(func.count()).select_from(Chunk)) == 0
            assert await session.scalar(select(func.count()).select_from(ChunkEmbedding)) == 0

    _migrate()
    asyncio.run(run())
