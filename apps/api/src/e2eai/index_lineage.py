"""Dataset/index lineage (FR-D10).

Every index version records its source document/version, parser, chunker, and embedding model.
Rows are written at ingest (idempotent per version + embedding model). Lineage is metadata only
(no titles, text, or vectors) and is read through the same SQL permission predicate as retrieval,
so a restricted document's lineage is indistinguishable from a missing one.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import current_session, require_scope
from .authz import principals
from .core.errors import AppError
from .db import Document, IndexLineage, User, get_session


def _row(item: IndexLineage) -> dict[str, Any]:
    return {
        "document_id": str(item.document_id),
        "version_id": str(item.version_id),
        "parser": item.parser,
        "chunker": item.chunker,
        "embedding_model": item.embedding_model,
        "chunk_count": item.chunk_count,
        "recorded_at": item.recorded_at.isoformat() if item.recorded_at else None,
    }


async def record_lineage(
    session: AsyncSession,
    *,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    parser: str,
    chunker: str,
    embedding_model: str,
    chunk_count: int,
) -> None:
    """Upsert the lineage row for (version, embedding model) and commit."""
    existing = await session.scalar(select(IndexLineage).where(
        IndexLineage.version_id == version_id, IndexLineage.embedding_model == embedding_model,
    ))
    if existing is None:
        session.add(IndexLineage(
            document_id=document_id, version_id=version_id, parser=parser, chunker=chunker,
            embedding_model=embedding_model, chunk_count=chunk_count,
        ))
    else:
        existing.parser, existing.chunker, existing.chunk_count = parser, chunker, chunk_count
        existing.recorded_at = func.now()
    await session.commit()


async def lineage_for_document(session: AsyncSession, document_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = (await session.execute(
        select(IndexLineage).where(IndexLineage.document_id == document_id).order_by(IndexLineage.recorded_at)
    )).scalars().all()
    return [_row(r) for r in rows]


async def visible_lineage(
    session: AsyncSession, *, user: User, document_id: uuid.UUID | None = None
) -> list[dict[str, Any]]:
    """Lineage rows for documents the user may see (permission predicate runs in SQL)."""
    from .documents import _visible_document_clause

    principal_list = sorted(set(await principals(session, user)))
    if not principal_list:
        return []
    stmt = (
        select(IndexLineage)
        .join(Document, Document.id == IndexLineage.document_id)
        .where(
            Document.status == "active",
            or_(Document.expires_at.is_(None), Document.expires_at > func.now()),
            _visible_document_clause(principal_list),
        )
        .order_by(IndexLineage.recorded_at, IndexLineage.embedding_model)
    )
    if document_id is not None:
        stmt = stmt.where(IndexLineage.document_id == document_id)
    return [_row(r) for r in (await session.execute(stmt)).scalars().all()]


async def lineage_summary(session: AsyncSession) -> dict[str, Any]:
    """Admin summary: index versions by embedding model/parser/chunker (counts only)."""

    async def grouped(column) -> dict[str, int]:
        rows = (await session.execute(select(column, func.count()).group_by(column))).all()
        return {str(key): int(count) for key, count in rows}

    total = await session.scalar(select(func.count()).select_from(IndexLineage)) or 0
    return {
        "index_versions": int(total),
        "by_embedding_model": await grouped(IndexLineage.embedding_model),
        "by_parser": await grouped(IndexLineage.parser),
        "by_chunker": await grouped(IndexLineage.chunker),
    }


router = APIRouter(prefix="/api/v1/lineage", tags=["lineage"])


async def _user(db: AsyncSession, sess: dict) -> User:
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None or user.status != "active":
        raise AppError(401, "Not authenticated")
    return user


@router.get("")
async def lineage_api(
    document_id: uuid.UUID | None = None,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """FR-D10: lineage of the documents the caller can access."""
    require_scope(sess, "documents")
    user = await _user(db, sess)
    return {"lineage": await visible_lineage(db, user=user, document_id=document_id)}


@router.get("/summary")
async def lineage_summary_api(
    sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """FR-D10: admin-only aggregate of index versions."""
    from .offboarding import _require_admin

    require_scope(sess, "admin")
    await _require_admin(db, sess)
    return await lineage_summary(db)
