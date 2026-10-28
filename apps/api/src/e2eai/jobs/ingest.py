"""Celery task: ingest one document version in the worker (FR-D3, FR-F20, PRD flow F1.4).

The task carries only the version id. The worker reads the stored object, scans, parses (Docling for rich files),
chunks, embeds and indexes it through the same `ingest_version` the API uses inline. Every run builds its own database
engine inside its own event loop: a cached engine would stay bound to a loop that `asyncio.run` already closed.
"""

import asyncio
import logging
import uuid

from celery import shared_task

from .. import audit
from ..core.errors import AppError

log = logging.getLogger("e2eai.jobs.ingest")
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5  # doubled on every retry, capped at 300 s


def _transient(exc: BaseException) -> bool:
    """Retry upstream hiccups (gateway restarting, database reconnecting); never retry a bad input."""
    import httpx

    if isinstance(exc, AppError):
        return exc.status >= 500
    return isinstance(exc, (OSError, TimeoutError, httpx.TransportError))  # ConnectionError is an OSError


async def run_ingest(version_id: uuid.UUID, embedder=None) -> dict:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from ..core.config import get_settings
    from ..documents import get_storage
    from ..ingest import ingest_version
    from ..retrieval import LiteLLMEmbedder

    engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            return await ingest_version(
                session, embedder=embedder or LiteLLMEmbedder.from_settings(), version_id=version_id, storage=get_storage()
            )
    finally:
        await engine.dispose()


async def mark_ingest_failed(version_id: uuid.UUID, reason: str) -> None:
    """After the last retry, leave an honest status instead of a version that stays `pending` forever."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from ..core.config import get_settings
    from ..db import DocumentVersion

    engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            version = await session.get(DocumentVersion, version_id)
            if version is not None and version.parse_status in ("pending", "indexing"):
                version.parse_status = "failed"
                await audit.record(session, "system:ingest", "document.parse.failed", f"document:{version.document_id}",
                                   {"version_id": str(version_id), "reason": reason})
                await session.commit()
    finally:
        await engine.dispose()


@shared_task(bind=True, name="e2eai.jobs.ingest.ingest_version_task", max_retries=MAX_RETRIES)
def ingest_version_task(self, version_id: str) -> dict:
    vid = uuid.UUID(version_id)  # malformed ids fail the task right away: nothing to mark
    try:
        result = asyncio.run(run_ingest(vid))
    except Exception as exc:  # noqa: BLE001
        if _transient(exc) and self.request.retries < MAX_RETRIES:
            delay = min(RETRY_DELAY_SECONDS * 2**self.request.retries, 300)
            log.warning("ingest %s: %s, retry %s/%s in %ss", vid, type(exc).__name__, self.request.retries + 1, MAX_RETRIES, delay)
            raise self.retry(exc=exc, countdown=delay) from exc
        log.error("ingest %s failed: %s", vid, type(exc).__name__)
        asyncio.run(mark_ingest_failed(vid, type(exc).__name__))
        raise
    return {"status": result["status"], "chunks": result["chunks"]}
