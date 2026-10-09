"""Versioned bot bundles and bot-scoped permission-aware answering (FR-RL1, FR-RL5, FR-RL7)."""

import uuid
from collections.abc import Sequence

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .auth import current_session, require_scope
from .authz import principals
from .core.errors import AppError
from .db import Bot, BotBundle, BotGrant, BotScope, User, get_session
from .retrieval import Embedder, LiteLLMEmbedder, answer_question


async def create_bot(session: AsyncSession, *, owner: User, name: str) -> Bot:
    if not name.strip():
        raise AppError(400, "Bot name is required")
    bot = Bot(name=name, owner_id=owner.id)
    session.add(bot)
    await session.flush()
    await audit.record(session, f"user:{owner.id}", "bot.create", f"bot:{bot.id}", {"name": name})
    await session.commit()
    return bot


async def release_bundle(session: AsyncSession, *, actor: User, bot_id: uuid.UUID, bundle: dict) -> BotBundle:
    bot = await _load_bot(session, bot_id)
    current = await session.get(BotBundle, bot.production_bundle_id) if bot.production_bundle_id else None
    if current:
        current.status = "superseded"
    version = (await session.scalar(select(func.max(BotBundle.version)).where(BotBundle.bot_id == bot_id))) or 0
    released = BotBundle(
        bot_id=bot_id,
        version=version + 1,
        status="production",
        bundle=dict(bundle),
        released_by=str(actor.id),
    )
    session.add(released)
    await session.flush()
    bot.production_bundle_id = released.id
    await audit.record(session, f"user:{actor.id}", "bot.bundle.release", f"bot:{bot_id}", {"version": released.version})
    await session.commit()
    return released


async def rollback_bundle(session: AsyncSession, *, actor: User, bot_id: uuid.UUID, target_bundle_id: uuid.UUID) -> BotBundle:
    bot = await _load_bot(session, bot_id)
    target = await session.get(BotBundle, target_bundle_id)
    if target is None or target.bot_id != bot_id:
        raise AppError(404, "Bundle not found")
    current = await session.get(BotBundle, bot.production_bundle_id) if bot.production_bundle_id else None
    if current and current.id != target.id:
        current.status = "rolled_back"
    target.status = "production"
    bot.production_bundle_id = target.id
    await audit.record(session, f"user:{actor.id}", "bot.bundle.rollback", f"bot:{bot_id}", {"target_version": target.version})
    await session.commit()
    return target


async def grant_bot_access(
    session: AsyncSession, *, actor: User, bot_id: uuid.UUID, principal: str, level: str = "user"
) -> BotGrant:
    await _load_bot(session, bot_id)
    grant = BotGrant(bot_id=bot_id, principal=principal, level=level)
    await session.merge(grant)
    await audit.record(session, f"user:{actor.id}", "bot.access.grant", f"bot:{bot_id}", {"principal": principal})
    await session.commit()
    return grant


async def set_bot_scope(
    session: AsyncSession,
    *,
    actor: User,
    bot_id: uuid.UUID,
    document_ids: Sequence[uuid.UUID] = (),
    folder_ids: Sequence[uuid.UUID] = (),
) -> None:
    await _load_bot(session, bot_id)
    await session.execute(delete(BotScope).where(BotScope.bot_id == bot_id))
    for document_id in document_ids:
        session.add(BotScope(bot_id=bot_id, target_type="document", target_id=document_id))
    for folder_id in folder_ids:
        session.add(BotScope(bot_id=bot_id, target_type="folder", target_id=folder_id))
    await audit.record(
        session,
        f"user:{actor.id}",
        "bot.scope.set",
        f"bot:{bot_id}",
        {"documents": len(document_ids), "folders": len(folder_ids)},
    )
    await session.commit()


async def answer_bot_question(
    session: AsyncSession,
    *,
    embedder: Embedder,
    user: User,
    bot_id: uuid.UUID,
    question: str,
    include_explainability: bool = False,
) -> dict:
    bot = await session.get(Bot, bot_id)
    if bot is None or bot.production_bundle_id is None:
        return {"answer": "I don't have access to that bot.", "citations": []}
    user_principals = await principals(session, user)
    allowed = await _user_has_bot_access(session, bot_id=bot_id, user_principals=user_principals)
    if not allowed:
        await audit.record(session, f"user:{user.id}", "bot.access.denied", f"bot:{bot_id}", {})
        await session.commit()
        return {"answer": "I don't have access to that bot.", "citations": []}
    scopes = list((await session.execute(select(BotScope).where(BotScope.bot_id == bot_id))).scalars().all())
    scoped_document_ids = [s.target_id for s in scopes if s.target_type == "document"]
    scoped_folder_ids = [s.target_id for s in scopes if s.target_type == "folder"]
    return await answer_question(
        session,
        embedder=embedder,
        user=user,
        question=question,
        scoped_document_ids=scoped_document_ids,
        scoped_folder_ids=scoped_folder_ids,
        include_explainability=include_explainability,
    )


async def _user_has_bot_access(session: AsyncSession, *, bot_id: uuid.UUID, user_principals: set[str]) -> bool:
    if not user_principals:
        return False
    return (await session.scalar(
        select(func.count()).select_from(BotGrant).where(BotGrant.bot_id == bot_id, BotGrant.principal.in_(sorted(user_principals)))
    )) > 0


async def _load_bot(session: AsyncSession, bot_id: uuid.UUID) -> Bot:
    bot = await session.get(Bot, bot_id)
    if bot is None:
        raise AppError(404, "Bot not found")
    return bot


async def _current_user(db: AsyncSession, sess: dict) -> User:
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None or user.status != "active":
        raise AppError(401, "Not authenticated")
    return user


class BotIn(BaseModel):
    name: str


class BundleIn(BaseModel):
    bundle: dict


class GrantIn(BaseModel):
    principal: str
    level: str = "user"


class ScopeIn(BaseModel):
    document_ids: list[uuid.UUID] = []
    folder_ids: list[uuid.UUID] = []


class BotAskIn(BaseModel):
    question: str
    include_explainability: bool = False


router = APIRouter(prefix="/api/v1/bots", tags=["bots"])


@router.post("")
async def create_bot_api(body: BotIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)) -> dict:
    require_scope(sess, "bots")
    user = await _current_user(db, sess)
    bot = await create_bot(db, owner=user, name=body.name)
    return {"id": str(bot.id), "name": bot.name}


@router.post("/{bot_id}/bundles")
async def release_bundle_api(bot_id: uuid.UUID, body: BundleIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)) -> dict:
    require_scope(sess, "bots")
    user = await _current_user(db, sess)
    bundle = await release_bundle(db, actor=user, bot_id=bot_id, bundle=body.bundle)
    return {"id": str(bundle.id), "version": bundle.version, "status": bundle.status}


@router.post("/{bot_id}/bundles/{bundle_id}/rollback")
async def rollback_bundle_api(bot_id: uuid.UUID, bundle_id: uuid.UUID, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)) -> dict:
    require_scope(sess, "bots")
    user = await _current_user(db, sess)
    bundle = await rollback_bundle(db, actor=user, bot_id=bot_id, target_bundle_id=bundle_id)
    return {"id": str(bundle.id), "version": bundle.version, "status": bundle.status}


@router.post("/{bot_id}/grants")
async def grant_bot_api(bot_id: uuid.UUID, body: GrantIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)) -> dict:
    require_scope(sess, "bots")
    user = await _current_user(db, sess)
    grant = await grant_bot_access(db, actor=user, bot_id=bot_id, principal=body.principal, level=body.level)
    return {"principal": grant.principal, "level": grant.level}


@router.put("/{bot_id}/scope")
async def set_bot_scope_api(bot_id: uuid.UUID, body: ScopeIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)) -> dict:
    require_scope(sess, "bots")
    user = await _current_user(db, sess)
    await set_bot_scope(db, actor=user, bot_id=bot_id, document_ids=body.document_ids, folder_ids=body.folder_ids)
    return {"status": "ok", "documents": len(body.document_ids), "folders": len(body.folder_ids)}


@router.post("/{bot_id}/ask")
async def ask_bot_api(bot_id: uuid.UUID, body: BotAskIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)) -> dict:
    from .auth import redis_client
    from .quotas import enforce_request_quota, enforce_token_quota, estimate_tokens, get_effective_policy, record_token_usage

    require_scope(sess, "bots")
    user = await _current_user(db, sess)
    if not body.question.strip():
        raise AppError(400, "Question is required")

    # FR-F13: enforce request + token quotas
    redis = redis_client()
    policy = await get_effective_policy(db, user=user)
    await enforce_request_quota(redis, user_id=sess["user_id"], endpoint="bot_ask", policy=policy)
    await enforce_token_quota(redis, user_id=sess["user_id"], estimated_tokens=estimate_tokens(body.question), policy=policy)

    result = await answer_bot_question(db, embedder=LiteLLMEmbedder.from_settings(), user=user, bot_id=bot_id, question=body.question, include_explainability=body.include_explainability)

    # Record token usage (best-effort)
    answer_tokens = estimate_tokens(result.get("answer", ""))
    await record_token_usage(redis, user_id=sess["user_id"], tokens=estimate_tokens(body.question) + answer_tokens)

    return result
