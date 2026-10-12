"""Load tests on model endpoints and the full chat API (FR-T10).

Deterministic/offline building blocks:
- `run_load_test` drives an injected async target with bounded concurrency (no network in tests).
- `summarize_samples` / `check_thresholds` compute latency percentiles, throughput, error rate and
  report SLO violations.
- `generate_k6_script` documents the real-load boundary (k6 is the default tool, PRD FR-T10). The script
  reads the base URL and API key from environment placeholders and never embeds URLs or credentials.
- Stored EvalRuns hold only latency/ok/status aggregates: no request bodies, response bodies, or
  exception text, so a load run cannot become a leakage channel.
"""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import current_session, require_scope
from .core.errors import AppError
from .db import EvalRun, get_session
from .eval_lab import _current_user, create_dataset

TARGETS = ("chat", "model")
MAX_SAMPLES = 100_000
_DURATION = re.compile(r"^\d{1,5}[smh]$")


def percentile(values: Sequence[float], pct: float) -> float:
    """Linear-interpolated percentile (the same convention as numpy's default)."""
    if not values:
        raise ValueError("percentile of an empty sequence")
    if not 0 <= pct <= 100:
        raise ValueError("percentile must be between 0 and 100")
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100) * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    return round(ordered[low] + (ordered[high] - ordered[low]) * (rank - low), 4)


def summarize_samples(samples: Sequence[dict], *, duration_s: float) -> dict[str, Any]:
    """Aggregate latency / throughput / error rate from {latency_ms, ok, status} samples."""
    total = len(samples)
    if total == 0:
        return {
            "requests": 0, "errors": 0, "error_rate": 0.0, "throughput_rps": 0.0,
            "latency_ms": None, "status_counts": {},
        }
    latencies = [float(s["latency_ms"]) for s in samples]
    errors = sum(1 for s in samples if not s.get("ok", False))
    duration = max(float(duration_s), 1e-9)
    return {
        "requests": total,
        "errors": errors,
        "error_rate": round(errors / total, 4),
        "throughput_rps": round(total / duration, 4),
        "latency_ms": {
            "min": round(min(latencies), 4),
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
            "p99": percentile(latencies, 99),
            "max": round(max(latencies), 4),
        },
        "status_counts": dict(sorted(Counter(str(s.get("status", "unknown")) for s in samples).items())),
    }


def check_thresholds(
    summary: dict[str, Any],
    *,
    p95_ms: float | None = None,
    error_rate: float | None = None,
    min_rps: float | None = None,
) -> dict[str, Any]:
    """Compare a summary to SLO thresholds; every violated metric is reported."""
    violations: list[dict[str, Any]] = []
    latency = summary.get("latency_ms") or {}
    if p95_ms is not None and latency and latency["p95"] > p95_ms:
        violations.append({"metric": "p95_ms", "limit": p95_ms, "actual": latency["p95"]})
    if error_rate is not None and summary.get("error_rate", 0.0) > error_rate:
        violations.append({"metric": "error_rate", "limit": error_rate, "actual": summary["error_rate"]})
    if min_rps is not None and summary.get("throughput_rps", 0.0) < min_rps:
        violations.append({"metric": "throughput_rps", "limit": min_rps, "actual": summary["throughput_rps"]})
    return {"passed": not violations, "violations": violations}


async def run_load_test(
    target: Callable[[int], Awaitable[int | None]],
    *,
    requests: int,
    concurrency: int,
) -> dict[str, Any]:
    """Call `target(i)` `requests` times with at most `concurrency` in flight.

    `target` returns an HTTP-like status (None counts as 200). Any exception is recorded as a failed
    sample with status "error"; the exception text is deliberately discarded.
    """
    if requests < 1 or requests > MAX_SAMPLES:
        raise ValueError("requests must be between 1 and 100000")
    if concurrency < 1:
        raise ValueError("concurrency must be >= 1")
    semaphore = asyncio.Semaphore(concurrency)
    samples: list[dict[str, Any]] = []

    async def one(index: int) -> None:
        async with semaphore:
            started = time.perf_counter()
            try:
                status = await target(index)
                code = 200 if status is None else int(status)
                ok, label = code < 400, code
            except Exception:  # noqa: BLE001 - never keep exception text
                ok, label = False, "error"
            samples.append({"latency_ms": round((time.perf_counter() - started) * 1000, 4), "ok": ok, "status": label})

    started_all = time.perf_counter()
    await asyncio.gather(*(one(i) for i in range(requests)))
    duration = time.perf_counter() - started_all
    return {"summary": summarize_samples(samples, duration_s=duration), "duration_s": round(duration, 4)}


def generate_k6_script(*, target: str, vus: int, duration: str, p95_ms: int) -> str:
    """Return a k6 script for the chat API or a model endpoint, with env placeholders only."""
    if target not in TARGETS:
        raise ValueError(f"target must be one of {TARGETS}")
    if not 1 <= int(vus) <= 10_000:
        raise ValueError("vus must be between 1 and 10000")
    if not _DURATION.match(duration or ""):
        raise ValueError("duration must look like 30s, 5m or 1h")
    if int(p95_ms) < 1:
        raise ValueError("p95_ms must be positive")

    header = f"""import http from 'k6/http';
import {{ check }} from 'k6';

export const options = {{
  vus: {int(vus)},
  duration: '{duration}',
  thresholds: {{
    http_req_duration: ['p(95)<{int(p95_ms)}'],
    http_req_failed: ['rate<0.01'],
  }},
}};

const BASE = __ENV.E2EAI_BASE_URL;
const HEADERS = {{
  'Content-Type': 'application/json',
  Authorization: `Bearer ${{__ENV.E2EAI_API_KEY}}`,
}};
"""
    if target == "chat":
        body = """
export default function () {
  const created = http.post(`${BASE}/api/v1/chat/conversations`, JSON.stringify({ title: 'load test' }), { headers: HEADERS });
  check(created, { 'conversation created': (r) => r.status === 200 });
  const id = created.json('id');
  const answer = http.post(
    `${BASE}/api/v1/chat/conversations/${id}/messages`,
    JSON.stringify({ question: 'What is the leave policy?' }),
    { headers: HEADERS },
  );
  check(answer, { 'answered': (r) => r.status === 200 });
}
"""
    else:
        body = """
export default function () {
  const res = http.post(
    `${BASE}/chat/completions`,
    JSON.stringify({ model: __ENV.E2EAI_MODEL, messages: [{ role: 'user', content: 'ping' }], max_tokens: 16 }),
    { headers: HEADERS },
  );
  check(res, { 'completion ok': (r) => r.status === 200 });
}
"""
    return header + body


async def evaluate_load_samples(
    session: AsyncSession,
    *,
    name: str,
    target: str,
    samples: Sequence[dict],
    duration_s: float,
    created_by: str,
    p95_ms: float | None = None,
    error_rate: float | None = None,
    min_rps: float | None = None,
    dataset_id: uuid.UUID | None = None,
) -> EvalRun:
    """Summarize client-collected samples against SLOs and store a safe EvalRun."""
    if target not in TARGETS:
        raise AppError(400, "Unknown load-test target")
    if len(samples) > MAX_SAMPLES:
        raise AppError(400, "Too many samples")
    if duration_s <= 0:
        raise AppError(400, "duration_s must be positive")
    clean: list[dict[str, Any]] = []
    for sample in samples:
        latency = sample.get("latency_ms")
        if isinstance(latency, bool) or not isinstance(latency, (int, float)) or latency < 0:
            raise AppError(400, "Each sample needs a non-negative latency_ms")
        clean.append({"latency_ms": float(latency), "ok": bool(sample.get("ok", False)), "status": sample.get("status", "unknown")})

    summary = summarize_samples(clean, duration_s=duration_s)
    verdict = check_thresholds(summary, p95_ms=p95_ms, error_rate=error_rate, min_rps=min_rps)
    metrics = {
        "target": target,
        "summary": summary,
        "thresholds": verdict,
        "adapter_boundary": {"mode": "offline_local", "external_runners": ["k6", "guidellm"], "imports_external_tools": False},
    }
    if dataset_id is None:
        ds = await create_dataset(
            session, name=name, items=[{"target": target, "requests": len(clean)}], source="load_test", created_by=created_by
        )
        dataset_id = ds.id
    run = EvalRun(
        dataset_id=dataset_id, adapter="load-test.local", status="completed",
        metrics=metrics, item_results=[], created_by=created_by,
    )
    session.add(run)
    await session.commit()
    return run


class LoadTestIn(BaseModel):
    name: str = "load-test"
    target: str
    samples: list[dict]
    duration_s: float
    dataset_id: uuid.UUID | None = None
    p95_ms: float | None = None
    error_rate: float | None = None
    min_rps: float | None = None


class K6ScriptIn(BaseModel):
    target: str
    vus: int = 10
    duration: str = "30s"
    p95_ms: int = 3000


router = APIRouter(prefix="/api/v1/evals", tags=["evals"])


@router.post("/load-test")
async def run_load_test_api(
    body: LoadTestIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """FR-T10: summarize client-collected load samples against SLO thresholds."""
    from .auth import redis_client
    from .quotas import enforce_request_quota, get_effective_policy

    require_scope(sess, "evals")
    user = await _current_user(db, sess)
    policy = await get_effective_policy(db, user=user)
    await enforce_request_quota(redis_client(), user_id=sess["user_id"], endpoint="evals.load_test", policy=policy)
    run = await evaluate_load_samples(
        db, name=body.name, target=body.target, samples=body.samples, duration_s=body.duration_s,
        created_by=f"user:{user.id}", p95_ms=body.p95_ms, error_rate=body.error_rate,
        min_rps=body.min_rps, dataset_id=body.dataset_id,
    )
    return {"id": str(run.id), "adapter": run.adapter, "metrics": run.metrics}


@router.post("/load-test/k6-script")
async def k6_script_api(body: K6ScriptIn, sess: dict = Depends(current_session)) -> dict:
    """FR-T10: k6 script with env placeholders (no URLs or credentials embedded)."""
    require_scope(sess, "evals")
    try:
        return {"tool": "k6", "script": generate_k6_script(
            target=body.target, vus=body.vus, duration=body.duration, p95_ms=body.p95_ms)}
    except ValueError as exc:
        raise AppError(400, str(exc)) from exc
