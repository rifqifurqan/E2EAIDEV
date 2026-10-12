"""FR-T10 load tests on model endpoints and the full chat API.

Deterministic/offline: a runner drives an injected async target (no network in tests), summarizes
latency percentiles / throughput / error rate, and checks SLO thresholds. A k6 script generator
documents the real-load boundary without embedding URLs or credentials.
"""

import asyncio
import subprocess

import pytest


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


def test_percentile_and_summary_statistics():
    from e2eai.load_test import percentile, summarize_samples

    values = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    assert percentile(values, 50) == 55.0
    assert percentile(values, 95) == 95.5
    assert percentile(values, 100) == 100.0
    assert percentile([42], 95) == 42.0
    with pytest.raises(ValueError):
        percentile([], 50)
    with pytest.raises(ValueError):
        percentile(values, 101)

    samples = [{"latency_ms": v, "ok": v != 100, "status": 200 if v != 100 else 500} for v in values]
    summary = summarize_samples(samples, duration_s=2.0)
    assert summary["requests"] == 10 and summary["errors"] == 1
    assert summary["error_rate"] == 0.1
    assert summary["throughput_rps"] == 5.0
    assert summary["latency_ms"] == {"min": 10.0, "p50": 55.0, "p95": 95.5, "p99": 99.1, "max": 100.0}
    assert summary["status_counts"] == {"200": 9, "500": 1}
    assert summarize_samples([], duration_s=1.0)["requests"] == 0


def test_slo_thresholds_report_each_violation():
    from e2eai.load_test import check_thresholds, summarize_samples

    samples = [{"latency_ms": 100.0, "ok": True, "status": 200}] * 9 + [{"latency_ms": 9000.0, "ok": False, "status": 503}]
    summary = summarize_samples(samples, duration_s=1.0)
    verdict = check_thresholds(summary, p95_ms=3000, error_rate=0.01, min_rps=20)
    assert verdict["passed"] is False
    assert sorted(v["metric"] for v in verdict["violations"]) == ["error_rate", "p95_ms", "throughput_rps"]
    ok = check_thresholds(summarize_samples(samples[:9], duration_s=0.1), p95_ms=3000, error_rate=0.01, min_rps=20)
    assert ok["passed"] is True and ok["violations"] == []


def test_runner_respects_concurrency_and_records_failures_without_leaking_error_text():
    from e2eai.load_test import run_load_test

    active = 0
    peak = 0
    calls = 0

    async def target(i: int):
        nonlocal active, peak, calls
        calls += 1
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        if i % 5 == 0:
            raise RuntimeError("boom token=abc123 Traceback")
        return 200

    result = asyncio.run(run_load_test(target, requests=20, concurrency=4))
    assert calls == 20
    assert peak <= 4
    assert result["summary"]["requests"] == 20
    assert result["summary"]["errors"] == 4
    assert "abc123" not in str(result) and "Traceback" not in str(result)
    assert result["summary"]["status_counts"].get("error") == 4

    with pytest.raises(ValueError):
        asyncio.run(run_load_test(target, requests=0, concurrency=1))
    with pytest.raises(ValueError):
        asyncio.run(run_load_test(target, requests=10, concurrency=0))


def test_k6_script_has_no_credentials_and_uses_env_placeholders():
    from e2eai.load_test import generate_k6_script

    script = generate_k6_script(target="chat", vus=10, duration="30s", p95_ms=3000)
    assert "export const options" in script and "p(95)<3000" in script
    assert "__ENV.E2EAI_BASE_URL" in script and "__ENV.E2EAI_API_KEY" in script
    assert "/api/v1/chat/conversations" in script
    assert "http://" not in script and "https://" not in script
    models = generate_k6_script(target="model", vus=2, duration="10s", p95_ms=8000)
    assert "/chat/completions" in models
    with pytest.raises(ValueError):
        generate_k6_script(target="other", vus=1, duration="1s", p95_ms=1)
    with pytest.raises(ValueError):
        generate_k6_script(target="chat", vus=1, duration="1s; rm -rf", p95_ms=1)


def test_stored_run_and_routes():
    async def run():
        from e2eai.db import sessions
        from e2eai.load_test import evaluate_load_samples

        samples = [{"latency_ms": 120.0 + i, "ok": True, "status": 200, "body": "SECRET-BODY"} for i in range(10)]
        async with sessions()() as session:
            row = await evaluate_load_samples(
                session, name="chat-load", target="chat", samples=samples, duration_s=2.0,
                created_by="test", p95_ms=3000, error_rate=0.05,
            )
            assert row.adapter == "load-test.local"
            assert row.metrics["thresholds"]["passed"] is True
            assert row.metrics["summary"]["requests"] == 10
            assert "SECRET-BODY" not in str(row.metrics) + str(row.item_results)

    _migrate()
    asyncio.run(run())

    from e2eai.main import app

    paths = app.openapi()["paths"]
    assert "post" in paths["/api/v1/evals/load-test"]
    assert "post" in paths["/api/v1/evals/load-test/k6-script"]
