"""Optional OpenAI-compatible endpoint: each bot is exposed as a "model" (FR-C15).

For external chat front-ends such as LibreChat. Rules:

- The caller authenticates as the end user (session cookie or the user's own API key); there is no
  shared service key path here.
- `model` is a bot id. A bot the user may not use is indistinguishable from a bot that does not exist
  (same 404), so bot existence is not leaked.
- The answer comes only from the permission-filtered bot pipeline (bot scope ∩ user permissions).
  The client's own `system` prompt, files, tools, and RAG parameters are ignored.
- Only the last user message is used as the question; earlier turns are not replayed into retrieval.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import current_session, require_scope
from .authz import principals
from .bot_release import answer_bot_question
from .core.errors import AppError
from .db import Bot, BotGrant, User, get_session
from .retrieval import Embedder

MAX_QUESTION_CHARS = 8000
NOT_FOUND = "The model does not exist or you do not have access to it."


def _tokens(text: str) -> int:
    return max(1, len(text) // 4) if text else 0


async def _usable_bot_ids(session: AsyncSession, user: User) -> list[uuid.UUID]:
    user_principals = sorted(await principals(session, user))
    if not user_principals:
        return []
    stmt = (
        select(Bot.id).join(BotGrant, BotGrant.bot_id == Bot.id)
        .where(BotGrant.principal.in_(user_principals), Bot.production_bundle_id.is_not(None))
        .distinct().order_by(Bot.id)
    )
    return list((await session.scalars(stmt)).all())


async def list_models(session: AsyncSession, *, user: User) -> dict[str, Any]:
    """`GET /models`: only bots with a production bundle that the user has been granted."""
    ids = await _usable_bot_ids(session, user)
    bots = {b.id: b for b in (await session.scalars(select(Bot).where(Bot.id.in_(ids)))).all()} if ids else {}
    return {
        "object": "list",
        "data": [
            {"id": str(i), "object": "model", "created": int(bots[i].created_at.timestamp()), "owned_by": "e2eai"}
            for i in ids if i in bots
        ],
    }


def _last_user_question(body: dict[str, Any]) -> str:
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise AppError(400, "messages is required")
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, list):  # OpenAI content parts: keep text parts only
                content = " ".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
            if not isinstance(content, str) or not content.strip():
                raise AppError(400, "The last user message is empty")
            if len(content) > MAX_QUESTION_CHARS:
                raise AppError(400, "The question is too long")
            return content.strip()
    raise AppError(400, "A user message is required")


async def chat_completion(
    session: AsyncSession, *, embedder: Embedder, user: User, body: dict[str, Any]
) -> dict[str, Any]:
    """`POST /chat/completions` (non-streaming body; streaming wraps this with `completion_to_sse`)."""
    question = _last_user_question(body)
    try:
        bot_id = uuid.UUID(str(body.get("model", "")))
    except ValueError as exc:
        raise AppError(404, "Model not found", NOT_FOUND) from exc
    if bot_id not in set(await _usable_bot_ids(session, user)):
        raise AppError(404, "Model not found", NOT_FOUND)
    result = await answer_bot_question(session, embedder=embedder, user=user, bot_id=bot_id, question=question)
    answer = str(result.get("answer", ""))
    prompt_tokens, completion_tokens = _tokens(question), _tokens(answer)
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": str(bot_id),
        "choices": [{"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
        "citations": list(result.get("citations", [])),
    }


def completion_to_sse(completion: dict[str, Any], *, chunk_size: int = 80) -> Iterator[str]:
    """Replay a finished completion as OpenAI-style SSE chunks ending with `data: [DONE]`."""
    content = completion["choices"][0]["message"]["content"]
    base = {k: completion[k] for k in ("id", "created", "model")} | {"object": "chat.completion.chunk"}

    def event(delta: dict, finish: str | None) -> str:
        payload = base | {"choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    yield event({"role": "assistant"}, None)
    for start in range(0, len(content), max(1, chunk_size)):
        yield event({"content": content[start:start + chunk_size]}, None)
    yield event({}, completion["choices"][0].get("finish_reason", "stop"))
    yield "data: [DONE]\n\n"


router = APIRouter(prefix="/api/v1/openai", tags=["openai-compatible"])


async def _user(db: AsyncSession, sess: dict) -> User:
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None or user.status != "active":
        raise AppError(401, "Not authenticated")
    return user


@router.get("/models")
async def models_api(sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)) -> dict:
    require_scope(sess, "chat")
    return await list_models(db, user=await _user(db, sess))


@router.post("/chat/completions")
async def completions_api(
    body: dict[str, Any], sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)
):
    from .auth import redis_client
    from .quotas import enforce_request_quota, enforce_token_quota, estimate_tokens, get_effective_policy, record_token_usage
    from .retrieval import LiteLLMEmbedder

    require_scope(sess, "chat")
    user = await _user(db, sess)
    question = _last_user_question(body)
    redis = redis_client()
    policy = await get_effective_policy(db, user=user)
    await enforce_request_quota(redis, user_id=sess["user_id"], endpoint="openai.chat", policy=policy)
    await enforce_token_quota(redis, user_id=sess["user_id"], estimated_tokens=estimate_tokens(question), policy=policy)
    completion = await chat_completion(db, embedder=LiteLLMEmbedder.from_settings(), user=user, body=body)
    await record_token_usage(redis, user_id=sess["user_id"], tokens=completion["usage"]["total_tokens"])
    if body.get("stream") is True:
        return StreamingResponse(completion_to_sse(completion), media_type="text/event-stream")
    return completion
