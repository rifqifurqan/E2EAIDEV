"""Chat conversations, message history, feedback, and stop marker (FR-C11, FR-O1, FR-O2, FR-C9, FR-C12).

TDD tests — written before the implementation. Each test proves a specific invariant:
- Owner-scoped CRUD: user sees only own conversations, rename/delete fail for non-owner
- Message + citation persistence through the existing permission-filtered answer_question path
- No-existence leak: Budi cannot see Andi's conversation or restricted document titles
- Feedback PII masking: correction text is masked, audit contains no raw PII
- Stop marker: recorded on the message without breaking history
"""

import asyncio
import subprocess

from sqlalchemy import delete, func, select

from e2eai.authz import principals
from e2eai.db import (
    AuditEntry,
    Chunk,
    ChunkEmbedding,
    Conversation,
    DocPrincipal,
    Document,
    DocumentVersion,
    Folder,
    Message,
    MessageCitation,
    MessageFeedback,
    User,
    sessions,
)
from e2eai.documents import create_seeded_document, share_document
from e2eai.retrieval import answer_question, index_document_chunks
from e2eai.seed import seed_demo


class RecordingAuthz:
    async def write(self, writes=(), deletes=()):
        return None


class FakeEmbedder:
    """Deterministic keyword one-hot embedder: proves retrieval ranks by vector distance."""

    model = "fake-embedding-v1"
    _axes = ("revenue", "holiday")

    async def embed(self, texts):
        return [[float(text.lower().count(axis)) for axis in self._axes] for text in texts]


async def _reset(session):
    for model in (MessageFeedback, MessageCitation, Message, Conversation,
                  ChunkEmbedding, DocPrincipal, Chunk, DocumentVersion, Document, Folder):
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


# ---------------------------------------------------------------------------
# 1. Owner-scoped CRUD: list / create / rename / delete
# ---------------------------------------------------------------------------
def test_user_sees_only_own_conversations_and_crud_is_owner_scoped():
    """FR-C11: list, search, rename, delete scoped to the owning user."""
    from e2eai.chat import (
        create_conversation,
        delete_conversation,
        list_conversations,
        rename_conversation,
    )

    async def run():
        async with sessions()() as session:
            await _reset(session)
            _owner, andi, budi = await _users(session)

            # Andi creates two conversations
            c1 = await create_conversation(session, user=andi, title="Revenue questions")
            c2 = await create_conversation(session, user=andi, title="Holiday planning")
            assert c1.user_id == andi.id
            assert c2.user_id == andi.id

            # Andi sees both
            andi_convos = await list_conversations(session, user=andi)
            assert len(andi_convos) == 2
            titles = {c.title for c in andi_convos}
            assert titles == {"Revenue questions", "Holiday planning"}

            # Budi sees none — no existence hint
            budi_convos = await list_conversations(session, user=budi)
            assert budi_convos == []

            # Search scoped to owner
            andi_search = await list_conversations(session, user=andi, search="Revenue")
            assert len(andi_search) == 1
            assert andi_search[0].title == "Revenue questions"

            budi_search = await list_conversations(session, user=budi, search="Revenue")
            assert budi_search == []

            # Rename scoped to owner
            await rename_conversation(session, user=andi, conversation_id=c1.id, new_title="Revenue Q&A")
            await session.refresh(c1)
            assert c1.title == "Revenue Q&A"

            # Budi cannot rename Andi's conversation
            try:
                await rename_conversation(session, user=budi, conversation_id=c1.id, new_title="Hijacked")
                assert False, "Should have raised"
            except Exception as exc:
                assert "404" in str(exc.status) or exc.status == 404

            # Delete scoped to owner
            await delete_conversation(session, user=andi, conversation_id=c2.id)
            andi_after = await list_conversations(session, user=andi)
            assert len(andi_after) == 1
            assert andi_after[0].title == "Revenue Q&A"

            # Budi cannot delete Andi's conversation
            try:
                await delete_conversation(session, user=budi, conversation_id=c1.id)
                assert False, "Should have raised"
            except Exception as exc:
                assert "404" in str(exc.status) or exc.status == 404

    _migrate()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# 2. Ask question stores messages + citations; Budi sees nothing
# ---------------------------------------------------------------------------
def test_ask_stores_messages_citations_and_budi_gets_no_leak():
    """FR-C11 + FR-C12: user message + assistant answer + citations persisted in the conversation.
    Budi has no access to Andi's conversation or the restricted document title."""
    from e2eai.chat import (
        create_conversation,
        list_conversations,
        send_message,
    )

    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi, budi = await _users(session)

            # Set up: Intern owns a document, shares with Andi only
            doc = await create_seeded_document(
                session, owner=owner,
                title="WhatsApp Partnership",
                text="The WhatsApp partnership revenue share is 30 percent.",
                page=4,
            )
            await share_document(session, RecordingAuthz(), actor=owner,
                                 document_id=doc.id, principal=f"user:{andi.id}")
            await index_document_chunks(session, embedder=FakeEmbedder(), document_id=doc.id)

            # Andi creates a conversation and asks
            conv = await create_conversation(session, user=andi, title="Revenue chat")
            result = await send_message(
                session, user=andi, conversation_id=conv.id,
                question="What is the revenue share?",
                embedder=FakeEmbedder(),
            )

            # Messages persisted: one user message + one assistant message
            msgs = (await session.execute(
                select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at)
            )).scalars().all()
            assert len(msgs) == 2
            assert msgs[0].role == "user"
            assert msgs[0].content == "What is the revenue share?"
            assert msgs[1].role == "assistant"
            assert "30 percent" in msgs[1].content

            # Citation persisted on the assistant message
            cites = (await session.execute(
                select(MessageCitation).where(MessageCitation.message_id == msgs[1].id)
            )).scalars().all()
            assert len(cites) == 1
            assert cites[0].page == 4

            # Result dict matches
            assert "30 percent" in result["answer"]
            assert result["citations"][0]["page"] == 4

            # Budi cannot see Andi's conversation
            budi_convos = await list_conversations(session, user=budi)
            assert budi_convos == []

            # Budi cannot send a message to Andi's conversation
            try:
                await send_message(
                    session, user=budi, conversation_id=conv.id,
                    question="What is the revenue share?",
                    embedder=FakeEmbedder(),
                )
                assert False, "Should have raised"
            except Exception as exc:
                assert exc.status == 404

            # Budi's own conversation answer has no leak
            budi_conv = await create_conversation(session, user=budi, title="Budi chat")
            budi_result = await send_message(
                session, user=budi, conversation_id=budi_conv.id,
                question="What is the revenue share?",
                embedder=FakeEmbedder(),
            )
            assert budi_result["citations"] == []
            assert "WhatsApp" not in budi_result["answer"]
            assert "30 percent" not in budi_result["answer"]

    _migrate()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# 3. Feedback stores masked correction, no raw PII in audit
# ---------------------------------------------------------------------------
def test_feedback_stores_masked_correction_and_no_raw_pii_in_audit():
    """FR-O2: thumbs up/down with optional correction, PII masked. Audit safe (FR-O9)."""
    from e2eai.chat import (
        create_conversation,
        record_feedback,
        send_message,
    )

    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi, _budi = await _users(session)

            doc = await create_seeded_document(
                session, owner=owner,
                title="Contact Info",
                text="Please contact admin@example.com for help.",
                page=1,
            )
            await share_document(session, RecordingAuthz(), actor=owner,
                                 document_id=doc.id, principal=f"user:{andi.id}")
            await index_document_chunks(session, embedder=FakeEmbedder(), document_id=doc.id)

            conv = await create_conversation(session, user=andi, title="Contact chat")
            await send_message(
                session, user=andi, conversation_id=conv.id,
                question="Who do I contact?",
                embedder=FakeEmbedder(),
            )

            # Get the assistant message
            asst_msg = await session.scalar(
                select(Message).where(
                    Message.conversation_id == conv.id, Message.role == "assistant"
                )
            )
            assert asst_msg is not None

            # Submit feedback with PII in the correction
            correction_with_pii = "The correct email is boss@corp.com and call +6281234567890"
            await record_feedback(
                session, user=andi, message_id=asst_msg.id,
                rating="down", correction=correction_with_pii,
            )

            # Feedback row: correction is PII-masked
            fb = await session.scalar(
                select(MessageFeedback).where(MessageFeedback.message_id == asst_msg.id)
            )
            assert fb is not None
            assert fb.rating == "down"
            assert "boss@corp.com" not in fb.correction_masked
            assert "[EMAIL]" in fb.correction_masked
            assert "+6281234567890" not in fb.correction_masked
            assert "[PHONE]" in fb.correction_masked

            # Audit row for feedback must not contain raw PII
            audit_row = await session.scalar(
                select(AuditEntry).where(AuditEntry.action == "chat.feedback").order_by(AuditEntry.seq.desc())
            )
            assert audit_row is not None
            details_str = str(audit_row.details)
            assert "boss@corp.com" not in details_str
            assert "+6281234567890" not in details_str
            assert audit_row.details.get("rating") == "down"
            assert audit_row.details.get("has_correction") is True

    _migrate()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# 4. Thumbs-up feedback (no correction) stores cleanly
# ---------------------------------------------------------------------------
def test_feedback_thumbs_up_without_correction():
    """FR-O2: thumbs up with no correction text."""
    from e2eai.chat import (
        create_conversation,
        record_feedback,
        send_message,
    )

    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi, _budi = await _users(session)

            doc = await create_seeded_document(
                session, owner=owner, title="FAQ", text="Our office opens at 9 AM.", page=1,
            )
            await share_document(session, RecordingAuthz(), actor=owner,
                                 document_id=doc.id, principal=f"user:{andi.id}")
            await index_document_chunks(session, embedder=FakeEmbedder(), document_id=doc.id)

            conv = await create_conversation(session, user=andi, title="Hours chat")
            await send_message(session, user=andi, conversation_id=conv.id,
                               question="When does the office open?", embedder=FakeEmbedder())

            asst_msg = await session.scalar(
                select(Message).where(Message.conversation_id == conv.id, Message.role == "assistant")
            )
            await record_feedback(session, user=andi, message_id=asst_msg.id, rating="up")

            fb = await session.scalar(select(MessageFeedback).where(MessageFeedback.message_id == asst_msg.id))
            assert fb.rating == "up"
            assert fb.correction_masked is None

    _migrate()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# 5. Stop marker recorded without breaking history (FR-C9)
# ---------------------------------------------------------------------------
def test_stop_marker_recorded():
    """FR-C9: a stop/cancel marker sets stop_reason on the message without deleting it."""
    from e2eai.chat import (
        create_conversation,
        mark_stop,
        send_message,
    )

    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi, budi = await _users(session)

            doc = await create_seeded_document(
                session, owner=owner, title="Doc", text="Some content for testing.", page=1,
            )
            await share_document(session, RecordingAuthz(), actor=owner,
                                 document_id=doc.id, principal=f"user:{andi.id}")
            await index_document_chunks(session, embedder=FakeEmbedder(), document_id=doc.id)

            conv = await create_conversation(session, user=andi, title="Stop test")
            await send_message(session, user=andi, conversation_id=conv.id,
                               question="Tell me about this doc", embedder=FakeEmbedder())

            asst_msg = await session.scalar(
                select(Message).where(Message.conversation_id == conv.id, Message.role == "assistant")
            )

            # Mark stop
            await mark_stop(session, user=andi, message_id=asst_msg.id)
            await session.refresh(asst_msg)
            assert asst_msg.stop_reason == "user_stop"

            # Message content is still there (history not broken)
            assert asst_msg.content is not None and len(asst_msg.content) > 0

            # Audit recorded
            audit_row = await session.scalar(
                select(AuditEntry).where(AuditEntry.action == "chat.stop").order_by(AuditEntry.seq.desc())
            )
            assert audit_row is not None

            # Budi cannot stop Andi's message
            try:
                await mark_stop(session, user=budi, message_id=asst_msg.id)
                assert False, "Should have raised"
            except Exception as exc:
                assert exc.status == 404

    _migrate()
    asyncio.run(run())


# ---------------------------------------------------------------------------
# 6. Budi cannot see Andi's conversation title or restricted document title
# ---------------------------------------------------------------------------
def test_budi_cannot_see_andi_conversation_or_document_title():
    """FR-C12: no existence leak — Budi gets no hint that Andi's conversation or the restricted
    document exists. The title of the restricted document never appears in Budi's responses."""
    from e2eai.chat import (
        create_conversation,
        list_conversations,
        send_message,
    )

    async def run():
        async with sessions()() as session:
            await _reset(session)
            owner, andi, budi = await _users(session)

            # Restricted document shared only with Andi
            doc = await create_seeded_document(
                session, owner=owner,
                title="Confidential Board Minutes Q3",
                text="The board approved a 50 million dollar acquisition.",
                page=2,
            )
            await share_document(session, RecordingAuthz(), actor=owner,
                                 document_id=doc.id, principal=f"user:{andi.id}")
            await index_document_chunks(session, embedder=FakeEmbedder(), document_id=doc.id)

            # Andi has a conversation about it
            andi_conv = await create_conversation(session, user=andi, title="Board review")
            await send_message(session, user=andi, conversation_id=andi_conv.id,
                               question="Tell me about the acquisition",
                               embedder=FakeEmbedder())

            # Budi sees zero conversations — no hint about "Board review" or "Confidential Board Minutes"
            budi_convos = await list_conversations(session, user=budi)
            assert budi_convos == []

            # Budi's own question gets no leak
            budi_conv = await create_conversation(session, user=budi, title="Budi questions")
            budi_result = await send_message(session, user=budi, conversation_id=budi_conv.id,
                                             question="Tell me about the acquisition",
                                             embedder=FakeEmbedder())
            assert "Confidential" not in budi_result["answer"]
            assert "Board Minutes" not in budi_result["answer"]
            assert "50 million" not in budi_result["answer"]
            assert budi_result["citations"] == []

    _migrate()
    asyncio.run(run())
