"""Chat conversations, message history, feedback, and stop marker (FR-C11, FR-O1, FR-O2, FR-C9).

Conversations are strictly user-owned: every list/search/rename/delete/send is scoped to the
authenticated user's own conversations. Non-owner access returns 404 with no existence hint (FR-C12).
Feedback corrections are PII-masked before persistence; audit rows store only ratings/flags, never
raw PII (FR-O9).
"""

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .auth import current_session, require_scope
from .core.errors import AppError
from .db import Conversation, Message, MessageCitation, MessageFeedback, User, get_session
from .pii import mask_text
from .retrieval import AnswerGenerator, Embedder, answer_question


# ---------------------------------------------------------------------------
# Service helpers
# ---------------------------------------------------------------------------

async def create_conversation(session: AsyncSession, *, user: User, title: str) -> Conversation:
    conv = Conversation(user_id=user.id, title=title)
    session.add(conv)
    await audit.record(session, f"user:{user.id}", "chat.conversation.create",
                       f"conversation:{conv.id}", {"title": title})
    await session.commit()
    return conv


async def list_conversations(
    session: AsyncSession, *, user: User, search: str | None = None
) -> list[Conversation]:
    stmt = select(Conversation).where(Conversation.user_id == user.id)
    if search:
        stmt = stmt.where(Conversation.title.ilike(f"%{search}%"))
    stmt = stmt.order_by(Conversation.updated_at.desc())
    return list((await session.execute(stmt)).scalars().all())


async def rename_conversation(
    session: AsyncSession, *, user: User, conversation_id: uuid.UUID, new_title: str
) -> Conversation:
    conv = await _own_conversation(session, user, conversation_id)
    old_title = conv.title
    conv.title = new_title
    await audit.record(session, f"user:{user.id}", "chat.conversation.rename",
                       f"conversation:{conversation_id}", {"from": old_title, "to": new_title})
    await session.commit()
    return conv


async def delete_conversation(
    session: AsyncSession, *, user: User, conversation_id: uuid.UUID
) -> None:
    conv = await _own_conversation(session, user, conversation_id)
    if conv.legal_hold:  # FR-D13: legal hold overrides user deletion and retention
        raise AppError(409, "Legal hold blocks deletion", "This conversation is under legal hold and cannot be deleted.")
    await session.delete(conv)
    await audit.record(session, f"user:{user.id}", "chat.conversation.delete",
                       f"conversation:{conversation_id}", {})
    await session.commit()


async def send_message(
    session: AsyncSession,
    *,
    user: User,
    conversation_id: uuid.UUID,
    question: str,
    embedder: Embedder,
    answer_generator: AnswerGenerator | None = None,
    scope: str = "all",
    document_id: uuid.UUID | None = None,
    include_explainability: bool = False,
    descriptors: list | None = None,
    executor=None,
    rewrite: bool = True,
) -> dict:
    """Add a user message, generate a permission-filtered answer, store the assistant message
    with citations, and return the answer dict. The existing `answer_question` does the retrieval,
    guardrail filtering, language detection (FR-C13), and audit (FR-C8, FR-C12).

    When ``descriptors`` (list of MCPServerDescriptor) are provided, the MCP planner selects
    relevant tools, the offline executor runs them, and safe tool-call records are persisted
    and audited linked to the assistant message (FR-X2). The ``executor`` defaults to
    ``OfflineExecutor`` when not supplied — no real MCP network calls are made.
    """
    from .mcp_tool_call import OfflineExecutor, execute_and_persist_tool_calls, plan_mcp_tool_calls

    conv = await _own_conversation(session, user, conversation_id)

    # FR-R6: conversation-aware query rewriting from this user's own earlier questions only.
    from .query_rewrite import rewrite_query

    rewrite_result = None
    if rewrite:
        prior_rows = (await session.execute(
            select(Message.content)
            .where(Message.conversation_id == conv.id, Message.role == "user")
            .order_by(Message.created_at.desc())
            .limit(6)
        )).scalars().all()
        rewrite_result = rewrite_query(question, list(reversed(prior_rows)))

    # Store user message
    user_msg = Message(conversation_id=conv.id, role="user", content=question)
    session.add(user_msg)
    await session.flush()

    # Generate answer through existing permission-filtered path
    result = await answer_question(session, embedder=embedder, user=user, question=question,
                                   answer_generator=answer_generator, scope=scope, document_id=document_id,
                                   include_explainability=include_explainability,
                                   retrieval_query=rewrite_result.rewritten if rewrite_result and rewrite_result.applied else None)
    result["query_rewrite"] = (rewrite_result.as_dict() if rewrite_result
                               else {"applied": False, "reason": "disabled"})

    # Store assistant message
    asst_msg = Message(conversation_id=conv.id, role="assistant", content=result["answer"])
    session.add(asst_msg)
    await session.flush()

    # Store citations linked to the assistant message
    for cite in result.get("citations", []):
        session.add(MessageCitation(
            message_id=asst_msg.id,
            page=cite.get("page"),
            section=cite.get("section"),
        ))

    # FR-X2: plan + execute + persist MCP tool calls when descriptors are provided
    tool_calls: list[dict] = []
    records: list = []
    if descriptors:
        records = plan_mcp_tool_calls(descriptors=descriptors, question=question)
        if records:
            _executor = executor if executor is not None else OfflineExecutor()
            tool_calls = await execute_and_persist_tool_calls(
                session,
                records=records,
                executor=_executor,
                message_id=asst_msg.id,
                actor=f"user:{user.id}",
            )

    await session.commit()
    result["tool_calls"] = tool_calls

    # FR-X6: build combined citations from document citations + live tool-call results.
    # execute_and_persist_tool_calls returns only sanitized summaries, so this never exposes raw
    # tokens, server URLs, credentials, request payloads, or response payloads.
    from .combined_citations import build_combined_citations
    result["combined_citations"] = build_combined_citations(
        doc_citations=result.get("citations", []),
        tool_call_results=tool_calls,
    )

    return result


async def record_feedback(
    session: AsyncSession,
    *,
    user: User,
    message_id: uuid.UUID,
    rating: str,
    correction: str | None = None,
) -> MessageFeedback:
    """FR-O2: thumbs up/down with optional correction. PII in the correction is masked before
    persistence (FR-O9). Audit stores only the rating flag and a boolean has_correction — never
    the raw correction text."""
    if rating not in ("up", "down"):
        raise AppError(400, "Invalid rating", "Use 'up' or 'down'.")
    msg = await _own_message(session, user, message_id)

    correction_masked = mask_text(correction) if correction else None

    fb = MessageFeedback(
        message_id=msg.id,
        rating=rating,
        correction_masked=correction_masked,
    )
    session.add(fb)
    await audit.record(
        session, f"user:{user.id}", "chat.feedback", f"message:{message_id}",
        {"rating": rating, "has_correction": correction is not None},
    )
    await session.commit()
    return fb


async def mark_stop(
    session: AsyncSession,
    *,
    user: User,
    message_id: uuid.UUID,
) -> Message:
    """FR-C9: record a stop/cancel marker on an assistant message without deleting it."""
    msg = await _own_message(session, user, message_id)
    msg.stop_reason = "user_stop"
    await audit.record(session, f"user:{user.id}", "chat.stop", f"message:{message_id}", {})
    await session.commit()
    return msg


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _own_conversation(session: AsyncSession, user: User, conversation_id: uuid.UUID) -> Conversation:
    """Load a conversation only if the user owns it. Returns 404 for non-owner (no existence hint)."""
    conv = await session.scalar(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user.id)
    )
    if conv is None:
        raise AppError(404, "Conversation not found")
    return conv


async def _own_message(session: AsyncSession, user: User, message_id: uuid.UUID) -> Message:
    """Load a message only if the user owns its parent conversation (no existence hint)."""
    msg = await session.scalar(
        select(Message).join(Conversation, Conversation.id == Message.conversation_id).where(
            Message.id == message_id, Conversation.user_id == user.id
        )
    )
    if msg is None:
        raise AppError(404, "Message not found")
    return msg


# ---------------------------------------------------------------------------
# API routes (PRD T7: Chat group)
# ---------------------------------------------------------------------------

async def _current_user(db: AsyncSession, sess: dict) -> User:
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None or user.status != "active":
        raise AppError(401, "Not authenticated")
    return user


class ConversationIn(BaseModel):
    title: str


class RenameIn(BaseModel):
    title: str


class MessageIn(BaseModel):
    question: str
    scope: str = "all"
    document_id: uuid.UUID | None = None
    include_explainability: bool = False
    rewrite_query: bool = True  # FR-R6: conversation-aware query rewriting (opt-out)


class FeedbackIn(BaseModel):
    rating: str
    correction: str | None = None


router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.get("/chat/conversations")
async def list_conversations_api(
    search: str | None = None,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    require_scope(sess, "chat")
    user = await _current_user(db, sess)
    convos = await list_conversations(db, user=user, search=search)
    return {"conversations": [
        {"id": str(c.id), "title": c.title, "created_at": c.created_at.isoformat(), "updated_at": c.updated_at.isoformat()}
        for c in convos
    ]}


@router.post("/chat/conversations")
async def create_conversation_api(
    body: ConversationIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    require_scope(sess, "chat")
    user = await _current_user(db, sess)
    conv = await create_conversation(db, user=user, title=body.title)
    return {"id": str(conv.id), "title": conv.title}


@router.patch("/chat/conversations/{conversation_id}")
async def rename_conversation_api(
    conversation_id: uuid.UUID,
    body: RenameIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    require_scope(sess, "chat")
    user = await _current_user(db, sess)
    conv = await rename_conversation(db, user=user, conversation_id=conversation_id, new_title=body.title)
    return {"id": str(conv.id), "title": conv.title}


@router.delete("/chat/conversations/{conversation_id}")
async def delete_conversation_api(
    conversation_id: uuid.UUID,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    require_scope(sess, "chat")
    user = await _current_user(db, sess)
    await delete_conversation(db, user=user, conversation_id=conversation_id)
    return {"status": "deleted"}


@router.post("/chat/conversations/{conversation_id}/messages")
async def send_message_api(
    conversation_id: uuid.UUID,
    body: MessageIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    from .auth import redis_client
    from .quotas import enforce_request_quota, enforce_token_quota, estimate_tokens, get_effective_policy, record_token_usage
    from .retrieval import LiteLLMEmbedder

    require_scope(sess, "chat")
    user = await _current_user(db, sess)
    if not body.question.strip():
        raise AppError(400, "Question is required")

    # FR-F13: enforce request + token quotas
    redis = redis_client()
    policy = await get_effective_policy(db, user=user)
    await enforce_request_quota(redis, user_id=sess["user_id"], endpoint="chat", policy=policy)
    await enforce_token_quota(redis, user_id=sess["user_id"], estimated_tokens=estimate_tokens(body.question), policy=policy)

    result = await send_message(
        db, user=user, conversation_id=conversation_id,
        question=body.question, embedder=LiteLLMEmbedder.from_settings(),
        scope=body.scope, document_id=body.document_id,
        include_explainability=body.include_explainability,
        rewrite=body.rewrite_query,
    )

    # Record token usage (best-effort)
    answer_tokens = estimate_tokens(result.get("answer", ""))
    await record_token_usage(redis, user_id=sess["user_id"], tokens=estimate_tokens(body.question) + answer_tokens)

    return result


@router.post("/messages/{message_id}/feedback")
async def feedback_api(
    message_id: uuid.UUID,
    body: FeedbackIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    require_scope(sess, "chat")
    user = await _current_user(db, sess)
    fb = await record_feedback(db, user=user, message_id=message_id,
                               rating=body.rating, correction=body.correction)
    return {"status": "ok", "rating": fb.rating}


@router.post("/messages/{message_id}/stop")
async def stop_api(
    message_id: uuid.UUID,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    require_scope(sess, "chat")
    user = await _current_user(db, sess)
    msg = await mark_stop(db, user=user, message_id=message_id)
    return {"status": "stopped", "stop_reason": msg.stop_reason}
