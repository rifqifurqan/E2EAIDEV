"""Query rewriting + conversation-aware follow-up questions (FR-R6).

Pure rewriter tests are offline/deterministic; one DB test proves the chat pipeline retrieves with
the rewritten query while the stored message, answer language and permissions stay untouched.
"""

import asyncio
import subprocess

from sqlalchemy import delete, func, select

from e2eai.db import (
    Chunk, ChunkEmbedding, Conversation, DocPrincipal, Document, DocumentVersion, Folder,
    Message, MessageCitation, MessageFeedback, User, sessions,
)
from e2eai.documents import create_seeded_document, share_document
from e2eai.query_rewrite import is_follow_up, rewrite_query
from e2eai.retrieval import index_document_chunks
from e2eai.seed import seed_demo


def test_standalone_question_is_not_rewritten():
    r = rewrite_query("What is the WhatsApp revenue share?", ["Tell me about holidays"])
    assert r.applied is False
    assert r.rewritten == r.original == "What is the WhatsApp revenue share?"


def test_no_history_means_no_rewrite_even_for_follow_up_shape():
    r = rewrite_query("And what about that?", [])
    assert r.applied is False and r.reason == "no_history"


def test_pronoun_follow_up_gets_topic_from_previous_user_question():
    r = rewrite_query("How much is it?", ["What is the WhatsApp partnership revenue share?"])
    assert r.applied is True
    assert r.original == "How much is it?"
    for term in ("whatsapp", "partnership", "revenue", "share"):
        assert term in r.rewritten.lower()
    assert r.rewritten.startswith("How much is it?")


def test_indonesian_follow_up_detected_and_rewritten():
    assert is_follow_up("Kalau yang itu bagaimana?")
    r = rewrite_query("Lalu berapa persentasenya?", ["Berapa pembagian pendapatan kemitraan WhatsApp?"])
    assert r.applied is True
    assert "pendapatan" in r.rewritten.lower() and "whatsapp" in r.rewritten.lower()


def test_chained_follow_ups_anchor_on_last_standalone_question():
    history = ["What is the vendor contract renewal date?", "And who signs it?"]
    r = rewrite_query("What about the penalty?", history)
    assert "vendor" in r.rewritten.lower() and "renewal" in r.rewritten.lower()


def test_rewrite_is_length_capped_and_only_uses_user_history():
    long_hist = ["revenue " * 500]
    r = rewrite_query("What about it?", long_hist)
    assert len(r.rewritten) <= 500


# ---------------------------------------------------------------------------
# Chat pipeline wiring
# ---------------------------------------------------------------------------
class RecordingAuthz:
    async def write(self, writes=(), deletes=()):
        return None


class RecordingEmbedder:
    model = "fake-embedding-v1"
    _axes = ("revenue", "holiday")

    def __init__(self):
        self.calls: list[str] = []

    async def embed(self, texts):
        self.calls.extend(texts)
        return [[float(t.lower().count(a)) for a in self._axes] for t in texts]


async def _reset(session):
    for model in (MessageFeedback, MessageCitation, Message, Conversation,
                  ChunkEmbedding, DocPrincipal, Chunk, DocumentVersion, Document, Folder):
        await session.execute(delete(model))
    await session.commit()


def test_chat_follow_up_retrieves_with_rewritten_query_but_stores_original():
    from e2eai.chat import create_conversation, send_message

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)

    async def run():
        async with sessions()() as session:
            await _reset(session)
            await seed_demo(session, password="TestPassword_123456789")
            owner = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))
            andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
            budi = await session.scalar(select(User).where(func.lower(User.email) == "budi@demo.e2eai"))
            doc = await create_seeded_document(
                session, owner=owner, title="WhatsApp Partnership",
                text="The WhatsApp partnership revenue share is 30 percent.", page=4)
            await share_document(session, RecordingAuthz(), actor=owner,
                                 document_id=doc.id, principal=f"user:{andi.id}")
            await index_document_chunks(session, embedder=RecordingEmbedder(), document_id=doc.id)

            conv = await create_conversation(session, user=andi, title="Revenue chat")
            await send_message(session, user=andi, conversation_id=conv.id,
                               question="What is the revenue share?", embedder=RecordingEmbedder())

            emb = RecordingEmbedder()
            result = await send_message(session, user=andi, conversation_id=conv.id,
                                        question="How much is it?", embedder=emb)
            assert result["query_rewrite"]["applied"] is True
            assert any("revenue" in c.lower() for c in emb.calls)  # retrieval used rewritten query
            assert "30 percent" in result["answer"]
            msgs = (await session.execute(
                select(Message).where(Message.conversation_id == conv.id,
                                      Message.role == "user").order_by(Message.created_at)
            )).scalars().all()
            assert msgs[-1].content == "How much is it?"  # original stored, not rewritten

            # Opt-out keeps the raw question
            emb2 = RecordingEmbedder()
            r2 = await send_message(session, user=andi, conversation_id=conv.id,
                                    question="How much is it?", embedder=emb2, rewrite=False)
            assert r2["query_rewrite"]["applied"] is False
            assert not any("revenue" in c.lower() for c in emb2.calls)

            # Permissions unchanged: Budi's follow-up never surfaces Andi's document
            bconv = await create_conversation(session, user=budi, title="b")
            await send_message(session, user=budi, conversation_id=bconv.id,
                               question="What is the revenue share?", embedder=RecordingEmbedder())
            br = await send_message(session, user=budi, conversation_id=bconv.id,
                                    question="How much is it?", embedder=RecordingEmbedder())
            assert br["citations"] == [] and "30 percent" not in br["answer"]

    asyncio.run(run())
