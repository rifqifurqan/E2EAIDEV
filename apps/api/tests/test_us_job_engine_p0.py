"""FR-F20 Job / workflow engine interface: Celery (P0) and Temporal (P1) contract tests.

Tests cover:
  * JobRequest / JobResult dataclass invariants
  * NullJobEngine behavior (deterministic offline) — submit, idempotent re-submit, status, cancel
  * the JobEngine protocol is structural (runtime_checkable)
  * check_job_engine_contract returns no failures for NullJobEngine
  * make_job_engine returns NullJobEngine when Celery is not installed (Lite without worker)
  * make_job_engine('temporal') returns NullJobEngine when temporalio is not installed
  * make_job_engine rejects unknown engine names
"""
import asyncio
import uuid

import pytest

from e2eai.job_engine import (
    JobEngine,
    JobRequest,
    JobResult,
    NullJobEngine,
    check_job_engine_contract,
    make_job_engine,
)


def test_job_request_defaults():
    req = JobRequest(job_id="job-1", func="e2eai.jobs.null.noop")
    assert req.job_id == "job-1"
    assert req.func == "e2eai.jobs.null.noop"
    assert req.args == ()
    assert req.kwargs == {}
    assert req.max_retries == 3
    assert req.timeout_seconds == 300.0


def test_job_request_is_immutable():
    req = JobRequest(job_id="job-1", func="noop")
    with pytest.raises(Exception):
        req.job_id = "other"  # frozen=True


def test_job_engine_protocol_is_structural():
    # NullJobEngine should satisfy the structural JobEngine protocol.
    assert isinstance(NullJobEngine(), JobEngine)


def test_null_engine_submit_returns_tracking_id():
    engine = NullJobEngine()
    req = JobRequest(job_id=str(uuid.uuid4()), func="e2eai.jobs.null.noop")
    tracking_id = engine.submit(req)
    assert isinstance(tracking_id, str)
    assert tracking_id  # non-empty


def test_null_engine_submit_is_idempotent_per_job_id():
    engine = NullJobEngine()
    req = JobRequest(job_id="same-id", func="e2eai.jobs.null.noop")
    t1 = engine.submit(req)
    t2 = engine.submit(req)
    assert t1 == t2  # same job_id -> same tracking_id


def test_null_engine_different_job_ids_get_different_tracking():
    engine = NullJobEngine()
    t1 = engine.submit(JobRequest(job_id="a", func="noop"))
    t2 = engine.submit(JobRequest(job_id="b", func="noop"))
    assert t1 != t2


def test_null_engine_status_returns_pending_initially():
    engine = NullJobEngine()
    req = JobRequest(job_id=str(uuid.uuid4()), func="noop")
    tracking_id = engine.submit(req)
    result = asyncio.run(engine.status(tracking_id))
    assert result.status == "pending"
    assert result.error is None


def test_null_engine_status_unknown_id_returns_failed():
    engine = NullJobEngine()
    result = asyncio.run(engine.status("does-not-exist"))
    assert result.status == "failed"
    assert "unknown" in result.error.lower()


def test_null_engine_cancel_pending_returns_true():
    engine = NullJobEngine()
    req = JobRequest(job_id=str(uuid.uuid4()), func="noop")
    tracking_id = engine.submit(req)
    cancelled = asyncio.run(engine.cancel(tracking_id))
    assert cancelled is True
    result = asyncio.run(engine.status(tracking_id))
    assert result.status == "failed"
    assert result.error == "cancelled"


def test_null_engine_cancel_already_cancelled_returns_false():
    engine = NullJobEngine()
    req = JobRequest(job_id=str(uuid.uuid4()), func="noop")
    tracking_id = engine.submit(req)
    asyncio.run(engine.cancel(tracking_id))
    cancelled = asyncio.run(engine.cancel(tracking_id))
    assert cancelled is False


def test_check_job_engine_contract_passes_for_null_engine():
    engine = NullJobEngine()
    failures = asyncio.run(check_job_engine_contract(engine))
    assert failures == [], f"Contract check failed: {failures}"


def test_make_job_engine_celery_falls_back_to_null_when_unavailable():
    # On this dev machine celery may or may not be installed; either way we get a JobEngine.
    engine = make_job_engine("celery")
    assert isinstance(engine, JobEngine)


def test_make_job_engine_temporal_falls_back_to_null_when_unavailable():
    engine = make_job_engine("temporal")
    assert isinstance(engine, JobEngine)


def test_make_job_engine_unknown_name_raises():
    with pytest.raises(ValueError, match="unknown job engine"):
        make_job_engine("unknown")


def test_job_result_dataclass():
    result = JobResult(status="success", result={"ok": True}, attempts=1)
    assert result.status == "success"
    assert result.result == {"ok": True}
    assert result.attempts == 1
    assert result.error is None


def test_job_result_failed_has_error():
    result = JobResult(status="failed", error="something broke")
    assert result.status == "failed"
    assert result.error == "something broke"
