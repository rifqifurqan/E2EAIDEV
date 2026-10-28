"""Decide where a freshly stored document version is parsed (FR-D3, FR-F20, PRD flow F1.4).

* Plain text / markdown is fast: it is ingested inline, so a tiny upload answers immediately.
* Rich files (PDF, DOCX, PPTX, XLSX, images) go to the background worker when one is listening.
* No worker online, or the broker fails while queueing: ingest inline instead. With Docling installed in this process
  that still works (slowly); without it the version is recorded `failed` with a clear reason, never lost.
"""

import asyncio
import inspect
import logging
import uuid

from .job_engine import JobEngine, JobRequest, NullJobEngine, make_job_engine

log = logging.getLogger("e2eai.ingest")
INGEST_TASK = "e2eai.jobs.ingest.ingest_version_task"


async def _inline(session, **kw) -> dict:
    from .ingest import ingest_version

    return await ingest_version(session, **kw)


def _configured_engine() -> JobEngine | None:
    """The real engine from e2eai.yaml, or None when it falls back to the do-nothing NullJobEngine."""
    from .core.config import get_settings

    engine = make_job_engine(get_settings().job_engine)
    return None if isinstance(engine, NullJobEngine) else engine


async def _default_worker_online() -> bool:
    from .celery_app import worker_online

    return await asyncio.to_thread(worker_online)


async def dispatch_ingest(
    session,
    *,
    version_id: uuid.UUID,
    mime: str,
    embedder,
    storage,
    engine: JobEngine | None = None,
    worker_online=None,
    inline_ingest=None,
) -> dict:
    inline = inline_ingest or _inline
    if not mime.startswith("text/"):
        engine = engine or _configured_engine()
        if engine is not None:
            online = (worker_online or _default_worker_online)()
            if inspect.isawaitable(online):
                online = await online
            if online:
                try:
                    request = JobRequest(job_id=f"ingest:{version_id}", func=INGEST_TASK, args=(str(version_id),))
                    await asyncio.to_thread(engine.submit, request)  # send_task does blocking network I/O
                    return {"status": "pending", "scan_status": None, "chunks": 0, "queued": True}
                except Exception as exc:  # noqa: BLE001 - never lose an upload over a queueing problem
                    log.warning("queueing ingest %s failed (%s); ingesting inline", version_id, type(exc).__name__)
    return await inline(session, embedder=embedder, version_id=version_id, storage=storage)
