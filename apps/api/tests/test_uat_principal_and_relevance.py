"""Live-UAT regressions (2026-10-14).

UAT-DOC-005: sharing with a malformed principal (`user:not-a-uuid`) was reported as success and
wrote a junk OpenFGA tuple + read-index row. The principal must be validated before any write.

UAT-CHAT-002: a question unrelated to every visible document ("president of Mars") still got the
nearest chunk back as the answer with a citation. Chunks below a minimum cosine similarity must not
be used as context, so the answer is the honest no-context message with no citation.
"""

import asyncio
import subprocess
import uuid

import pytest
from sqlalchemy import delete, func, select

from e2eai.core.errors import AppError
from e2eai.db import (
    Chunk, ChunkEmbedding, Conversation, DocPrincipal, Document, DocumentVersion, Folder, Message,
    MessageCitation, MessageFeedback, User, sessions,
)
from e2eai.documents import create_seeded_document, share_document
from e2eai.retrieval import answer_question, index_document_chunks
from e2eai.seed import seed_demo
from e2eai.share_policy import validate_principal


class RecordingAuthz:
    def __init__(self):
        self.calls = []

    async def write(self, writes=(), deletes=()):
        self.calls.append({"writes": list(writes), "deletes": list(deletes)})


# --- UAT-DOC-005: principal validation (pure + service, no DB) -------------------------------

@pytest.mark.parametrize("bad", [
    "user:not-a-uuid", "user:", "user", "team:123", "org:abc", "role:", "division:x y",
    "nobody:" + str(uuid.uuid4()), "guest:", "guest:not-an-email", "", "user:" + str(uuid.uuid4()) + ":extra",
])
def test_validate_principal_rejects_malformed(bad):
    with pytest.raises(AppError) as exc:
        validate_principal(bad)
    assert exc.value.status == 422


@pytest.mark.parametrize("good", [
    f"user:{uuid.uuid4()}", f"team:{uuid.uuid4()}", f"division:{uuid.uuid4()}",
    f"role:{uuid.uuid4()}", f"org:{uuid.uuid4()}", "guest:partner@external.com",
])
def test_validate_principal_accepts_wellformed(good):
    assert validate_principal(good) == good


def test_share_document_with_malformed_principal_writes_nothing():
    authz = RecordingAuthz()

    async def run():
        with pytest.raises(AppError) as exc:
            await share_document(None, authz, actor=None, document_id=uuid.uuid4(), principal="user:not-a-uuid")
        assert exc.value.status == 422

    asyncio.run(run())
    assert authz.calls == [], "a malformed principal must not reach OpenFGA"


# --- UAT-CHAT-002: relevance floor -------------------------------------------------------------

class AxisEmbedder:
    model = "fake-axis-v1"
    _axes = ("revenue", "holiday", "weather")

    async def embed(self, texts):
        return [[float(t.lower().count(a)) for a in self._axes] for t in texts]


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


async def _reset(session):
    # message_citations now reference documents, so conversations go first; every DB test here also
    # calls _reset() on exit so this file never leaves rows that block other suites' document cleanup.
    for model in (MessageFeedback, MessageCitation, Message, Conversation,
                  ChunkEmbedding, DocPrincipal, Chunk, DocumentVersion, Document, Folder):
        await session.execute(delete(model))
    await session.commit()


def test_unrelated_question_gets_no_context_and_no_citation_but_related_one_is_cited():
    async def run():
        async with sessions()() as session:
            await _reset(session)
            await seed_demo(session, password="TestPassword_123456789")
            andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
            doc = await create_seeded_document(
                session, owner=andi, title="Deal", text="The revenue share is 30 percent.")
            await index_document_chunks(session, embedder=AxisEmbedder(), document_id=doc.id)

            related = await answer_question(session, embedder=AxisEmbedder(), user=andi,
                                            question="What is the revenue share?")
            assert related["citations"] and related["citations"][0]["document"] == "Deal"

            unrelated = await answer_question(session, embedder=AxisEmbedder(), user=andi,
                                              question="What is the weather on Mars?")
            assert unrelated["citations"] == []
            assert "30 percent" not in unrelated["answer"]

            unrelated_id = await answer_question(session, embedder=AxisEmbedder(), user=andi,
                                                 question="Bagaimana weather di Mars yang tidak ada di dokumen?")
            assert unrelated_id["citations"] == []
            assert unrelated_id["answer"].startswith("Saya tidak menemukan")
            await _reset(session)

    _migrate()
    asyncio.run(run())


# --- UAT-CHAT-003/004: message ids for feedback + owner-scoped history ---------------------------

def test_send_message_returns_message_id_and_history_is_owner_scoped():
    from e2eai.chat import create_conversation, list_messages, send_message

    async def run():
        async with sessions()() as session:
            await _reset(session)
            await seed_demo(session, password="TestPassword_123456789")
            andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
            budi = await session.scalar(select(User).where(func.lower(User.email) == "budi@demo.e2eai"))
            doc = await create_seeded_document(
                session, owner=andi, title="Deal", text="The revenue share is 30 percent.")
            await index_document_chunks(session, embedder=AxisEmbedder(), document_id=doc.id)
            conv = await create_conversation(session, user=andi, title="Revenue")

            result = await send_message(session, user=andi, conversation_id=conv.id,
                                        question="What is the revenue share?", embedder=AxisEmbedder())
            assert uuid.UUID(result["message_id"])  # assistant message id, needed for feedback/stop

            history = await list_messages(session, user=andi, conversation_id=conv.id)
            assert [m["role"] for m in history] == ["user", "assistant"]
            assert history[0]["content"] == "What is the revenue share?"
            assert history[1]["id"] == result["message_id"]
            assert history[1]["citations"][0]["document"] == "Deal"  # history keeps the cited document name

            with pytest.raises(AppError) as exc:  # no existence hint for another user's conversation
                await list_messages(session, user=budi, conversation_id=conv.id)
            assert exc.value.status == 404
            await _reset(session)

    _migrate()
    asyncio.run(run())


def test_me_returns_session_csrf_token_so_the_web_can_sign_out_after_reload():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from e2eai.auth import current_session, router
    from e2eai.core.errors import install

    async def find():
        async with sessions()() as s:
            await seed_demo(s, password="TestPassword_123456789")
            return (await s.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))).id

    uid = asyncio.run(find())
    app = FastAPI()
    install(app)
    app.include_router(router)

    async def fake_session():
        return {"user_id": str(uid), "auth_type": "session", "csrf": "csrf-123", "sid": "s"}

    app.dependency_overrides[current_session] = fake_session
    body = TestClient(app, raise_server_exceptions=False).get("/api/v1/me").json()
    assert body["email"] == "andi@demo.e2eai"
    assert body["csrf_token"] == "csrf-123"


# --- UAT-DOC-006: trash view so a trashed document can be found and restored ---------------------

def test_trash_view_lists_only_the_owners_trashed_documents_and_restore_brings_them_back():
    from e2eai.documents import list_documents_view, restore_document, trash_document

    async def run():
        async with sessions()() as session:
            await _reset(session)
            await seed_demo(session, password="TestPassword_123456789")
            andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
            budi = await session.scalar(select(User).where(func.lower(User.email) == "budi@demo.e2eai"))
            keep = await create_seeded_document(session, owner=andi, title="keep.txt", text="keep me")
            gone = await create_seeded_document(session, owner=andi, title="gone.txt", text="trash me")
            await trash_document(session, actor=andi, document_id=gone.id)

            mine = await list_documents_view(session, user=andi, view="my_documents")
            assert [d["title"] for d in mine] == ["keep.txt"]

            trash = await list_documents_view(session, user=andi, view="trash")
            assert [(d["title"], d["status"]) for d in trash] == [("gone.txt", "trashed")]

            assert await list_documents_view(session, user=budi, view="trash") == []  # no existence hint

            await restore_document(session, actor=andi, document_id=gone.id)
            assert await list_documents_view(session, user=andi, view="trash") == []
            assert {d["title"] for d in await list_documents_view(session, user=andi, view="my_documents")} == {"keep.txt", "gone.txt"}
            assert keep.id != gone.id
            await _reset(session)

    _migrate()
    asyncio.run(run())
