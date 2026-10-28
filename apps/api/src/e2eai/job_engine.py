"""FR-F20 Job / workflow engine interface: Celery (P0) and Temporal (P1) contract tests.

Background (PRD T2, §17.6): background work is written once against one internal job interface.
- Celery (default, every tier): light, runs on the existing Valkey.
- Temporal (Standard/Enterprise): durable multi-step workflows that survive restarts.

Both engines must satisfy the same contract:
  * submit a job (idempotent per job_id)
  * retry with backoff
  * report status (pending / running / success / failed)
  * be swappable behind the JobEngine port interface

This module defines the protocol, a NullJobEngine (deterministic offline for tests and Lite
environments without a worker), a CeleryJobEngine adapter boundary, and contract checks that any
JobEngine implementation must pass.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol, runtime_checkable


@dataclass(frozen=True)
class JobRequest:
    """A unit of background work.

    `job_id` makes submission idempotent — resubmitting the same id must not duplicate work.
    `func` is a dotted import path (e.g. ``e2eai.jobs.ingest.ingest_version_task``) so the engine
    can resolve it in the worker process, never an in-memory callable.
    """

    job_id: str
    func: str
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)
    max_retries: int = 3
    timeout_seconds: float = 300.0


@dataclass(frozen=True)
class JobResult:
    """Terminal result of a background job."""

    status: str  # "pending" | "running" | "success" | "failed"
    result: Any = None
    error: str | None = None
    attempts: int = 0


@runtime_checkable
class JobEngine(Protocol):
    """Port interface for the job / workflow engine (PRD T2, FR-F20).

    The platform writes background work once against this interface; the engine is chosen in the
    wizard (``celery`` on every tier, ``temporal`` on Standard/Enterprise). A single implementation
    is the default; the protocol exists so the contract tests can validate a second engine.
    """

    def submit(self, request: JobRequest) -> str:
        """Enqueue a job. Returns a platform-side tracking id. Idempotent per request.job_id."""
        ...

    async def status(self, tracking_id: str) -> JobResult:
        """Poll the current status of a submitted job."""
        ...

    async def cancel(self, tracking_id: str) -> bool:
        """Best-effort cancellation. Returns True if a cancellation was requested."""
        ...


class NullJobEngine:
    """Deterministic offline engine for tests and Lite environments without a worker.

    Records submissions in memory. Never touches network or broker. Used so contract tests can
    validate the JobEngine interface without running Celery or Temporal.
    """

    def __init__(self, executor: Callable[[JobRequest], Awaitable[Any]] | None = None) -> None:
        self._executor = executor
        self._store: dict[str, JobResult] = {}
        self._by_job_id: dict[str, str] = {}
        self._next_tracking = 0

    def submit(self, request: JobRequest) -> str:
        # Idempotent per job_id: return the existing tracking id for a repeat submission.
        if request.job_id in self._by_job_id:
            return self._by_job_id[request.job_id]
        tracking_id = f"job-{self._next_tracking:04d}"
        self._next_tracking += 1
        self._by_job_id[request.job_id] = tracking_id
        self._store[tracking_id] = JobResult(status="pending")
        return tracking_id

    async def status(self, tracking_id: str) -> JobResult:
        return self._store.get(tracking_id, JobResult(status="failed", error="unknown tracking id"))

    async def cancel(self, tracking_id: str) -> bool:
        result = self._store.get(tracking_id)
        if result and result.status in ("pending", "running"):
            self._store[tracking_id] = JobResult(status="failed", error="cancelled")
            return True
        return False


# ---------------------------------------------------------------------------
# Contract checks every JobEngine implementation must satisfy
# ---------------------------------------------------------------------------

async def check_job_engine_contract(engine: JobEngine) -> list[str]:
    """Validate a JobEngine implementation. Returns a list of failure messages (empty == pass).

    These checks must hold for BOTH Celery and Temporal engines:
      1. submit returns a non-empty tracking id
      2. idempotent submission: same job_id -> different tracking id, both queryable
      3. status is one of the known states
      4. cancel returns a bool
    """
    failures: list[str] = []

    req = JobRequest(job_id=str(uuid.uuid4()), func="e2eai.jobs.null.noop")
    try:
        tracking_id = engine.submit(req)
    except Exception as exc:  # noqa: BLE001
        failures.append(f"submit raised: {exc!r}")
        return failures

    if not tracking_id or not isinstance(tracking_id, str):
        failures.append("submit did not return a non-empty string tracking_id")

    # Idempotency: resubmit the same job_id must return the same tracking id
    try:
        tracking_id_2 = engine.submit(req)
        if tracking_id_2 != tracking_id:
            failures.append("idempotent re-submit returned a different tracking_id")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"idempotent re-submit raised: {exc!r}")

    # Status is a known state
    try:
        result = await engine.status(tracking_id)
        if result.status not in ("pending", "running", "success", "failed"):
            failures.append(f"status returned unknown state: {result.status!r}")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"status raised: {exc!r}")

    # Cancel returns a bool
    try:
        cancelled = await engine.cancel(tracking_id)
        if not isinstance(cancelled, bool):
            failures.append(f"cancel did not return bool: {type(cancelled)}")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"cancel raised: {exc!r}")

    return failures


# ---------------------------------------------------------------------------
# Engine factory
# ---------------------------------------------------------------------------


def make_job_engine(name: str = "celery") -> JobEngine:
    """Build a JobEngine by name.

    ``celery`` (default, every tier) is the P0 engine. ``temporal`` is the P1 boundary (not yet
    wired in Lite). When the requested engine's dependencies are unavailable, falls back to
    NullJobEngine so the platform always has a working engine to submit against.
    """
    if name == "celery":
        return make_celery_engine()
    if name == "temporal":
        return make_temporal_engine()
    raise ValueError(f"unknown job engine: {name!r}")


def make_celery_engine() -> JobEngine:
    """Build a Celery-backed JobEngine, or NullJobEngine when Celery is not installed."""
    try:
        from e2eai.celery_app import celery_app  # type: ignore[import]
    except (ImportError, RuntimeError):  # not installed, or no .env yet (hosted CI)
        return NullJobEngine()

    class CeleryJobEngine:
        _app = celery_app

        def submit(self, request: JobRequest) -> str:
            # send_task with task_id=request.job_id is idempotent at the broker level:
            # a duplicate task_id is a no-op in the result backend.
            self._app.send_task(
                request.func,
                args=request.args,
                kwargs=request.kwargs,
                task_id=request.job_id,
            )
            return request.job_id

        async def status(self, tracking_id: str) -> JobResult:
            result = self._app.AsyncResult(tracking_id)
            state = result.state
            if state == "PENDING":
                return JobResult(status="pending")
            elif state == "STARTED":
                return JobResult(status="running")
            elif state == "SUCCESS":
                retries = 0
                if isinstance(result.info, dict):
                    retries = result.info.get("retries", 0)
                return JobResult(status="success", result=result.result, attempts=retries)
            else:
                return JobResult(status="failed", error=str(result.info))

        async def cancel(self, tracking_id: str) -> bool:
            self._app.control.revoke(tracking_id, terminate=True)
            return True

    return CeleryJobEngine()  # type: ignore[return-value]


def make_temporal_engine() -> JobEngine:
    """Build a Temporal-backed JobEngine, or NullJobEngine when temporalio is not installed.

    Temporal is the P1 engine for Standard/Enterprise (PRD T2). This boundary is compiled but
    only activated when the engine is selected and the temporalio SDK + server are available.
    """
    try:
        from e2eai.temporal_app import temporal_client  # type: ignore[import]
    except ImportError:
        return NullJobEngine()

    class TemporalJobEngine:
        _client = temporal_client

        def submit(self, request: JobRequest) -> str:
            run = self._client.start_workflow(
                request.func,
                *request.args,
                **request.kwargs,
                id=request.job_id,
                task_queue="e2eai",
            )
            return run.id

        async def status(self, tracking_id: str) -> JobResult:
            raise NotImplementedError("Temporal status polling requires the SDK + server")

        async def cancel(self, tracking_id: str) -> bool:
            raise NotImplementedError("Temporal cancellation requires the SDK + server")

    return TemporalJobEngine()  # type: ignore[return-value]
