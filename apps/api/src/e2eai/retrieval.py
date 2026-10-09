"""Permission-filtered retrieval and cited-answer generation for Phase 1.

Retrieval is pgvector-backed: the question is embedded through the same embedder as the chunks, and
candidates are ranked by cosine distance (`<=>`) in SQL. The P0 invariant holds inside that one query:
doc_principals is filtered in the WHERE clause *before* the ORDER BY/LIMIT, never as a post-top-k pass,
so unshared users get no document names, snippets, or citations.

Answer language (FR-C13): the AI answers in the language of the question. Language detection is
deterministic and runs on the question only — retrieved context cannot override it. Citations and
quotes stay in the original source language.
"""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Callable, Protocol

import httpx
import yaml
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .auth import current_session
from .authz import principals
from .core.config import Settings, get_settings, repo_root
from .core.errors import AppError
from .db import Chunk, ChunkEmbedding, DocPrincipal, Document, FolderPrincipal, User, get_session
from .guardrails import PromptGuardPolicy, PromptInjectionDetector, select_prompt_detector
from .language import detect_language

class Embedder(Protocol):
    @property
    def model(self) -> str: ...

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class LiteLLMEmbedder:
    """OpenAI-compatible LiteLLM embedding client for the local model gateway (FR-R1/FR-C1)."""

    base_url: str
    api_key: str
    model: str
    timeout: float = 120.0
    client_factory: Callable[..., Any] = httpx.AsyncClient

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "LiteLLMEmbedder":
        settings = settings or get_settings()
        cfg = yaml.safe_load((repo_root() / "e2eai.yaml").read_text(encoding="utf-8"))
        models = cfg.get("models", {}).get("embedding") or []
        if not models:
            raise AppError(503, "No embedding model configured")
        return cls(base_url=settings.litellm_url, api_key=settings.litellm_key, model=models[0])

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        async with self.client_factory(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.post(
                "/v1/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "input": list(texts)},
            )
        response.raise_for_status()
        data = response.json().get("data") or []
        vectors = [[float(value) for value in row.get("embedding", [])] for row in data]
        if len(vectors) != len(texts) or any(not vector for vector in vectors):
            raise AppError(502, "Embedding gateway returned an invalid response")
        return vectors


class AnswerGenerator(Protocol):
    async def generate(self, question: str, chunks: list[dict], answer_language: str) -> str: ...


def build_answer_system_prompt(chunks: list[dict], answer_language: str) -> str:
    """Build the system prompt for LLM answer generation with an explicit language instruction (FR-C13).

    The language instruction is derived from the question only (not from source content), so an injected
    "answer in X" instruction in retrieved context cannot override it.
    """
    language_name = "Indonesian" if answer_language == "id" else "English"
    context_lines = []
    for c in chunks:
        context_lines.append(
            f"[Source: {c['document']}, page {c['page']}, section: {c['section']}]\n{c['text']}"
        )
    context_block = "\n\n".join(context_lines)
    return (
        f"You are a helpful assistant. Answer questions using ONLY the provided sources.\n\n"
        f"IMPORTANT: You MUST answer in {language_name}.\n"
        f"When quoting or citing source text, keep quotes in their original language — "
        f"do not translate document titles, section names, or direct quotes from source material.\n\n"
        f"Sources:\n{context_block}"
    )


@dataclass(frozen=True)
class LiteLLMAnswerGenerator:
    """OpenAI-compatible LiteLLM chat client for answer generation with language control (FR-C13)."""

    base_url: str
    api_key: str
    model: str
    timeout: float = 120.0
    client_factory: Callable[..., Any] = httpx.AsyncClient

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "LiteLLMAnswerGenerator":
        settings = settings or get_settings()
        cfg = yaml.safe_load((repo_root() / "e2eai.yaml").read_text(encoding="utf-8"))
        models = cfg.get("models", {}).get("chat") or []
        if not models:
            raise AppError(503, "No chat model configured")
        return cls(base_url=settings.litellm_url, api_key=settings.litellm_key, model=models[0])

    async def generate(self, question: str, chunks: list[dict], answer_language: str) -> str:
        system_prompt = build_answer_system_prompt(chunks, answer_language)
        async with self.client_factory(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": question},
                    ],
                },
            )
        response.raise_for_status()
        choices = response.json().get("choices") or []
        if not choices:
            raise AppError(502, "Chat gateway returned no choices")
        return choices[0].get("message", {}).get("content", "")


async def index_document_chunks(session: AsyncSession, *, embedder: Embedder, document_id: uuid.UUID) -> int:
    """Embed all current chunks for one document once, independent of shares (FR-C1)."""
    rows = (
        await session.execute(
            select(Chunk)
            .join(Document, Document.id == Chunk.document_id)
            .where(Document.id == document_id, Document.current_version_id == Chunk.version_id)
            .order_by(Chunk.ordinal)
        )
    ).scalars().all()
    if not rows:
        return 0
    vectors = await embedder.embed([row.text for row in rows])
    for chunk, vector in zip(rows, vectors, strict=True):
        await session.merge(
            ChunkEmbedding(
                chunk_id=chunk.id,
                embedding_model=embedder.model,
                dims=len(vector),
                vector=[float(x) for x in vector],
            )
        )
    await audit.record(session, "system:ingest", "document.index", f"document:{document_id}", {"chunks": len(rows)})
    await session.commit()
    return len(rows)


async def retrieve_relevant_chunks(
    session: AsyncSession,
    *,
    embedder: Embedder,
    user_principals: Iterable[str],
    question: str,
    limit: int = 4,
    user: User | None = None,
    scope: str = "all",
    document_id: uuid.UUID | None = None,
    scoped_document_ids: Sequence[uuid.UUID] | None = None,
    scoped_folder_ids: Sequence[uuid.UUID] | None = None,
) -> list[dict]:
    """Rank indexed chunks by vector distance after SQL-level permission and scope filtering (FR-C2/FR-C3).

    Direct document shares and inherited folder shares are part of the SQL predicate before ordering/limit.
    Scopes only narrow this already-permission-filtered set; they never grant access.
    """
    principal_list = sorted(set(user_principals))
    if not principal_list:
        return []
    qvec = (await embedder.embed([question]))[0]
    allowed = _visible_document_clause(principal_list)
    filters = [
        Document.status == "active",
        Chunk.version_id == Document.current_version_id,
        ChunkEmbedding.embedding_model == embedder.model,
        allowed,
    ]
    if scope == "this_document":
        if document_id is None:
            return []
        filters.append(Document.id == document_id)
    elif scope == "my_documents":
        if user is None:
            return []
        filters.append(Document.owner_id == user.id)
    elif scope == "shared_with_me":
        if user is None:
            return []
        direct_user = f"user:{user.id}"
        filters.extend([
            Document.owner_id != user.id,
            or_(
                exists().where(DocPrincipal.document_id == Document.id, DocPrincipal.principal == direct_user),
                exists().where(FolderPrincipal.folder_id == Document.folder_id, FolderPrincipal.principal == direct_user),
            ),
        ])
    elif scope == "my_team":
        teams = sorted(p for p in principal_list if p.startswith("team:"))
        if not teams:
            return []
        filters.append(or_(
            exists().where(DocPrincipal.document_id == Document.id, DocPrincipal.principal.in_(teams)),
            exists().where(FolderPrincipal.folder_id == Document.folder_id, FolderPrincipal.principal.in_(teams)),
        ))
    elif scope not in ("all", "everything"):
        raise AppError(400, "Invalid chat scope")
    if scoped_document_ids is not None or scoped_folder_ids is not None:
        doc_ids = list(scoped_document_ids or [])
        folder_ids = list(scoped_folder_ids or [])
        if not doc_ids and not folder_ids:
            return []
        scope_filters = []
        if doc_ids:
            scope_filters.append(Document.id.in_(doc_ids))
        if folder_ids:
            scope_filters.append(Document.folder_id.in_(folder_ids))
        filters.append(or_(*scope_filters))
    rows = await session.execute(
        select(Document.title, Chunk.text, Chunk.page, Chunk.section_path)
        .join(Chunk, Chunk.document_id == Document.id)
        .join(ChunkEmbedding, ChunkEmbedding.chunk_id == Chunk.id)
        .where(*filters)
        .order_by(ChunkEmbedding.vector.cosine_distance(qvec))
        .limit(limit)
    )
    return [
        {"document": title, "text": text, "page": page, "section": section_path}
        for title, text, page, section_path in rows.all()
    ]


def _non_expired(expires_at_col):
    """Filter: expires_at is NULL (permanent) or in the future (FR-S4)."""
    return or_(expires_at_col.is_(None), expires_at_col > func.now())


def _visible_document_clause(principal_list: list[str]):
    return or_(
        exists().where(
            DocPrincipal.document_id == Document.id,
            DocPrincipal.principal.in_(principal_list),
            _non_expired(DocPrincipal.expires_at),
        ),
        exists().where(
            FolderPrincipal.folder_id == Document.folder_id,
            FolderPrincipal.principal.in_(principal_list),
            _non_expired(FolderPrincipal.expires_at),
        ),
    )


async def answer_question(
    session: AsyncSession,
    *,
    embedder: Embedder,
    user: User,
    question: str,
    prompt_detector: PromptInjectionDetector | None = None,
    prompt_policy: PromptGuardPolicy | None = None,
    answer_generator: AnswerGenerator | None = None,
    scope: str = "all",
    document_id: uuid.UUID | None = None,
    scoped_document_ids: Sequence[uuid.UUID] | None = None,
    scoped_folder_ids: Sequence[uuid.UUID] | None = None,
) -> dict:
    """Answer from permission-filtered chunks, treating retrieved context as untrusted (FR-C8).

    Answer language (FR-C13): the language is detected from the question only (never from retrieved
    context, so injected "answer in X" instructions in source text have no effect). When an
    answer_generator is provided, the answer is generated in the detected language; otherwise the
    top chunk text is returned directly (tracer-bullet fallback). Citations always stay in the
    original source language.
    """
    prompt_policy = prompt_policy or PromptGuardPolicy.from_settings()
    prompt_detector = prompt_detector or select_prompt_detector(prompt_policy)
    chunks = await retrieve_relevant_chunks(
        session,
        embedder=embedder,
        user_principals=await principals(session, user),
        question=question,
        limit=4,
        user=user,
        scope=scope,
        document_id=document_id,
        scoped_document_ids=scoped_document_ids,
        scoped_folder_ids=scoped_folder_ids,
    )
    safe_chunks = []
    for chunk in chunks:
        if prompt_policy.enabled and prompt_policy.block_suspicious_context:
            result = prompt_detector.detect(chunk["text"])
            if result.blocked:
                await audit.record(
                    session,
                    f"user:{user.id}",
                    "retrieval.context.blocked",
                    "retrieval:visible_chunks",
                    {"reasons": list(result.reasons), "reason_count": len(result.reasons)},
                )
                continue
        safe_chunks.append(chunk)
    answer_lang = detect_language(question)
    if not safe_chunks:
        no_context_msg = (
            "Saya tidak menemukan dokumen yang relevan untuk pertanyaan tersebut."
            if answer_lang == "id"
            else "I don't have access to relevant documents for that question."
        )
        await audit.record(session, f"user:{user.id}", "chat.answer.no_context", "retrieval:visible_chunks", {})
        await session.commit()
        return {"answer": no_context_msg, "answer_language": answer_lang, "citations": []}
    if answer_generator is not None:
        answer_text = await answer_generator.generate(question, safe_chunks, answer_lang)
    else:
        answer_text = safe_chunks[0]["text"]
    top = safe_chunks[0]
    await audit.record(session, f"user:{user.id}", "chat.answer", "retrieval:visible_chunks", {"citations": 1})
    await session.commit()
    return {
        "answer": answer_text,
        "answer_language": answer_lang,
        "citations": [{"document": top["document"], "page": top["page"], "section": top["section"]}],
    }


async def _current_user(db: AsyncSession, sess: dict) -> User:
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None or user.status != "active":
        raise AppError(401, "Not authenticated")
    return user


class AskIn(BaseModel):
    question: str
    scope: str = "all"
    document_id: uuid.UUID | None = None


router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat/ask")
async def ask(body: AskIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)) -> dict:
    from .auth import redis_client
    from .quotas import enforce_request_quota, enforce_token_quota, estimate_tokens, get_effective_policy, record_token_usage

    user = await _current_user(db, sess)
    if not body.question.strip():
        raise AppError(400, "Question is required")

    # FR-F13: enforce request + token quotas
    redis = redis_client()
    policy = await get_effective_policy(db, user=user)
    await enforce_request_quota(redis, user_id=sess["user_id"], endpoint="chat_ask", policy=policy)
    await enforce_token_quota(redis, user_id=sess["user_id"], estimated_tokens=estimate_tokens(body.question), policy=policy)

    result = await answer_question(
        db,
        embedder=LiteLLMEmbedder.from_settings(),
        user=user,
        question=body.question,
        scope=body.scope,
        document_id=body.document_id,
    )

    # Record token usage (best-effort)
    answer_tokens = estimate_tokens(result.get("answer", ""))
    await record_token_usage(redis, user_id=sess["user_id"], tokens=estimate_tokens(body.question) + answer_tokens)

    return result
