"""FR-F20 / PRD T1-T2: Celery is the real P0 job engine; rich-document ingestion runs in the worker.

No broker or database is needed here: the Celery app is only inspected, and the engine / worker probe are faked.
"""

import asyncio
import uuid

import pytest

from e2eai.job_engine import JobRequest, NullJobEngine, check_job_engine_contract, make_job_engine

VERSION_ID = uuid.UUID("01a181b1-b892-7c87-95fd-c3a8292dd716")


# --- settings -----------------------------------------------------------------------------------

def test_celery_uses_its_own_valkey_databases_apart_from_sessions():
    from e2eai.core.config import get_settings

    s = get_settings()
    base = s.valkey_url.rsplit("/", 1)[0]
    assert s.celery_broker_url.startswith(base + "/") and s.celery_result_url.startswith(base + "/")
    dbs = {s.valkey_url.rsplit("/", 1)[1], s.celery_broker_url.rsplit("/", 1)[1], s.celery_result_url.rsplit("/", 1)[1]}
    assert len(dbs) == 3, "sessions, broker and results must not share a Valkey database"


# --- the Celery app -----------------------------------------------------------------------------

def test_celery_app_registers_the_ingest_task_and_uses_safe_defaults():
    from e2eai.celery_app import celery_app

    celery_app.loader.import_default_modules()
    assert "e2eai.jobs.ingest.ingest_version_task" in celery_app.tasks
    conf = celery_app.conf
    assert conf.task_serializer == "json" and list(conf.accept_content) == ["json"]  # never pickle
    assert conf.task_acks_late is True and conf.worker_prefetch_multiplier == 1
    assert conf.task_time_limit and conf.task_time_limit >= 300
    assert conf.broker_connection_retry_on_startup is True


def test_a_real_celery_engine_is_built_and_honours_the_job_contract(monkeypatch):
    from e2eai.celery_app import celery_app

    sent = {}
    monkeypatch.setattr(celery_app, "send_task", lambda name, **kw: sent.setdefault(kw["task_id"], (name, kw)))
    engine = make_job_engine("celery")
    assert not isinstance(engine, NullJobEngine)
    assert asyncio.run(check_job_engine_contract(engine)) == []
    assert len(sent) == 1, "re-submitting the same job_id must not enqueue a second task"


# --- is a worker listening? ---------------------------------------------------------------------

def test_worker_online_is_true_only_when_a_worker_replies(monkeypatch):
    from e2eai import celery_app as mod

    monkeypatch.setattr(mod.celery_app.control, "ping", lambda timeout=1.0: [{"worker@pc": {"ok": "pong"}}])
    assert mod.worker_online() is True
    monkeypatch.setattr(mod.celery_app.control, "ping", lambda timeout=1.0: [])
    assert mod.worker_online() is False


def test_worker_online_is_false_when_the_broker_is_unreachable(monkeypatch):
    from e2eai import celery_app as mod

    def boom(timeout=1.0):
        raise OSError("connection refused")

    monkeypatch.setattr(mod.celery_app.control, "ping", boom)
    assert mod.worker_online() is False


# --- dispatch: queue rich files when a worker is listening, otherwise ingest inline -------------

class _Spy:
    def __init__(self):
        self.inline = []

    async def inline_ingest(self, session, **kw):
        self.inline.append(kw["version_id"])
        return {"status": "ready", "scan_status": "clean", "chunks": 3}


def _dispatch(spy, *, mime, worker, engine=None, submit_raises=False):
    from e2eai.ingest_dispatch import dispatch_ingest

    if submit_raises:
        class _Broken(NullJobEngine):
            def submit(self, request):
                raise OSError("broker went away")
        engine = _Broken()
    engine = engine or NullJobEngine()
    result = asyncio.run(dispatch_ingest(
        None, version_id=VERSION_ID, mime=mime, embedder=object(), storage=object(),
        engine=engine, worker_online=lambda: worker, inline_ingest=spy.inline_ingest,
    ))
    return result, engine


def test_text_files_are_always_ingested_inline_even_with_a_worker_online():
    spy = _Spy()
    result, engine = _dispatch(spy, mime="text/markdown", worker=True)
    assert result["status"] == "ready" and spy.inline == [VERSION_ID] and not engine._by_job_id


def test_rich_files_are_queued_when_a_worker_is_online():
    spy = _Spy()
    result, engine = _dispatch(spy, mime="application/pdf", worker=True)
    assert result == {"status": "pending", "scan_status": None, "chunks": 0, "queued": True}
    assert spy.inline == [] and f"ingest:{VERSION_ID}" in engine._by_job_id


def test_the_queued_job_names_the_task_and_carries_only_the_version_id():
    spy = _Spy()
    seen = []

    class _Recorder(NullJobEngine):
        def submit(self, request: JobRequest):
            seen.append(request)
            return super().submit(request)

    _dispatch(spy, mime="application/pdf", worker=True, engine=_Recorder())
    (req,) = seen
    assert req.func == "e2eai.jobs.ingest.ingest_version_task" and req.args == (str(VERSION_ID),)
    assert req.job_id == f"ingest:{VERSION_ID}" and not req.kwargs  # no file content or text goes through the broker


def test_rich_files_fall_back_to_inline_when_no_worker_is_online():
    spy = _Spy()
    result, engine = _dispatch(spy, mime="application/pdf", worker=False)
    assert spy.inline == [VERSION_ID] and result["status"] == "ready" and not engine._by_job_id


def test_a_broker_failure_while_queueing_falls_back_to_inline():
    spy = _Spy()
    result, _ = _dispatch(spy, mime="application/pdf", worker=True, submit_raises=True)
    assert spy.inline == [VERSION_ID] and result["status"] == "ready"


# --- the task itself ----------------------------------------------------------------------------

def test_the_task_ingests_the_given_version_and_returns_a_small_summary(monkeypatch):
    from e2eai.jobs import ingest as job

    async def fake_run(version_id):
        assert version_id == VERSION_ID
        return {"status": "ready", "scan_status": "clean", "chunks": 7, "indexed": 7, "pii_findings": 0}

    monkeypatch.setattr(job, "run_ingest", fake_run)
    assert job.ingest_version_task.apply(args=(str(VERSION_ID),)).get() == {"status": "ready", "chunks": 7}


def test_a_permanent_failure_marks_the_version_failed_instead_of_leaving_it_pending(monkeypatch):
    from e2eai.jobs import ingest as job

    marked = []

    async def fake_run(version_id):
        raise ValueError("corrupt state")  # not transient: no retry

    async def fake_mark(version_id, reason):
        marked.append((version_id, reason))

    monkeypatch.setattr(job, "run_ingest", fake_run)
    monkeypatch.setattr(job, "mark_ingest_failed", fake_mark)
    result = job.ingest_version_task.apply(args=(str(VERSION_ID),))
    assert result.failed() and marked == [(VERSION_ID, "ValueError")]


def test_a_transient_failure_is_retried_before_giving_up(monkeypatch):
    from e2eai.jobs import ingest as job

    calls = []

    async def flaky(version_id):
        calls.append(version_id)
        if len(calls) < 3:
            raise ConnectionError("gateway restarting")
        return {"status": "ready", "scan_status": "clean", "chunks": 1}

    monkeypatch.setattr(job, "run_ingest", flaky)
    monkeypatch.setattr(job, "RETRY_DELAY_SECONDS", 0)
    result = job.ingest_version_task.apply(args=(str(VERSION_ID),))
    assert result.successful() and len(calls) == 3


@pytest.mark.parametrize("bad", ["", "not-a-uuid"])
def test_the_task_rejects_a_malformed_version_id(bad):
    from e2eai.jobs import ingest as job

    assert job.ingest_version_task.apply(args=(bad,)).failed()
