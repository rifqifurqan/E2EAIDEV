"""Permission-filtered retrieval and cited-answer tracer bullet for Phase 1.

Retrieval is pgvector-backed: the question is embedded through the same embedder as the chunks, and
candidates are ranked by cosine distance (`<=>`) in SQL. The P0 invariant holds inside that one query:
doc_principals is filtered in the WHERE clause *before* the ORDER BY/LIMIT, never as a post-top-k pass,
so unshared users get no document names, snippets, or citations.
"""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Callable, Protocol

import httpx
import yaml
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .auth import current_session
from .authz import principals
from .core.config import Settings, get_settings, repo_root
from .core.errors import AppError
from .db import Chunk, ChunkEmbedding, DocPrincipal, Document, User, get_session
from .guardrails import PromptGuardPolicy, PromptInjectionDetector, select_prompt_detector

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
) -> list[dict]:
    """Rank indexed chunks by vector distance, after SQL-level permission filtering (FR-C2).

    The doc_principals join + WHERE restrict candidates *before* the ORDER BY/LIMIT, so the vector
    search only ever ranks chunks the caller may see. The ChunkEmbedding join is inner: un-indexed
    chunks are not retrievable, and unshared users match no rows at all.
    """
    principal_list = sorted(set(user_principals))
    if not principal_list:
        return []
    qvec = (await embedder.embed([question]))[0]
    rows = await session.execute(
        select(Document.title, Chunk.text, Chunk.page, Chunk.section_path)
        .join(Chunk, Chunk.document_id == Document.id)
        .join(ChunkEmbedding, ChunkEmbedding.chunk_id == Chunk.id)
        .join(DocPrincipal, DocPrincipal.document_id == Document.id)
        .where(
            Document.status == "active",
            Chunk.version_id == Document.current_version_id,
            ChunkEmbedding.embedding_model == embedder.model,
            DocPrincipal.principal.in_(principal_list),
        )
        .order_by(ChunkEmbedding.vector.cosine_distance(qvec))
        .limit(limit)
    )
    return [
        {"document": title, "text": text, "page": page, "section": section_path}
        for title, text, page, section_path in rows.all()
    ]


async def answer_question(
    session: AsyncSession,
    *,
    embedder: Embedder,
    user: User,
    question: str,
    prompt_detector: PromptInjectionDetector | None = None,
    prompt_policy: PromptGuardPolicy | None = None,
) -> dict:
    """Answer from permission-filtered chunks, treating retrieved context as untrusted (FR-C8).

    Suspicious retrieved chunks are audited and excluded before answer assembly. The audit stores only
    reason labels/counts, never the blocked text/title, and the user receives no citation/text if every
    candidate is blocked.
    """
    prompt_policy = prompt_policy or PromptGuardPolicy.from_settings()
    prompt_detector = prompt_detector or select_prompt_detector(prompt_policy)
    chunks = await retrieve_relevant_chunks(
        session, embedder=embedder, user_principals=await principals(session, user), question=question, limit=4
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
    if not safe_chunks:
        await audit.record(session, f"user:{user.id}", "chat.answer.no_context", "retrieval:visible_chunks", {})
        await session.commit()
        return {"answer": "I don't have access to relevant documents for that question.", "citations": []}
    top = safe_chunks[0]
    await audit.record(session, f"user:{user.id}", "chat.answer", "retrieval:visible_chunks", {"citations": 1})
    await session.commit()
    return {
        "answer": top["text"],
        "citations": [{"document": top["document"], "page": top["page"], "section": top["section"]}],
    }


async def _current_user(db: AsyncSession, sess: dict) -> User:
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None or user.status != "active":
        raise AppError(401, "Not authenticated")
    return user


class AskIn(BaseModel):
    question: str


router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat/ask")
async def ask(body: AskIn, sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)) -> dict:
    user = await _current_user(db, sess)
    if not body.question.strip():
        raise AppError(400, "Question is required")
    return await answer_question(db, embedder=LiteLLMEmbedder.from_settings(), user=user, question=body.question)
