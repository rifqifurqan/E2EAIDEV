"""NFR-16/NFR-19: readiness reports dependency state; required failures -> 503, optional -> degraded."""

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from e2eai.core.readiness import Check, make_ready_router, run_checks


async def _ok():
    return None


async def _boom():
    raise RuntimeError("connect postgresql://u:secret-pw@internal-host:5432/db failed")


async def _slow():
    await asyncio.sleep(5)


def test_all_ok_is_ready():
    result = _run([Check("db", _ok, required=True), Check("llm", _ok, required=False)])
    assert result["status"] == "ready"
    assert result["checks"] == {"db": "ok", "llm": "ok"}


def test_optional_failure_degrades_but_stays_ready():
    result = _run([Check("db", _ok, required=True), Check("langfuse", _boom, required=False)])
    assert result["status"] == "degraded"
    assert result["checks"]["langfuse"] == "unavailable"


def test_required_failure_is_not_ready():
    result = _run([Check("openfga", _boom, required=True), Check("db", _ok, required=True)])
    assert result["status"] == "not_ready"
    assert result["checks"]["openfga"] == "unavailable"


def test_timeout_counts_as_unavailable():
    result = _run([Check("valkey", _slow, required=True)], timeout=0.05)
    assert result["status"] == "not_ready"
    assert result["checks"]["valkey"] == "unavailable"


def test_result_never_contains_error_text_or_secrets():
    result = _run([Check("db", _boom, required=True)])
    text = str(result)
    assert "secret-pw" not in text and "internal-host" not in text and "RuntimeError" not in text


def _run(checks, **kw):
    return asyncio.run(run_checks(checks, **kw))


def _client(checks):
    app = FastAPI()
    app.include_router(make_ready_router(lambda: checks))
    return TestClient(app)


def test_endpoint_returns_503_when_required_dependency_down():
    r = _client([Check("openfga", _boom, required=True)]).get("/api/v1/ready")
    assert r.status_code == 503
    assert r.json()["status"] == "not_ready"


def test_endpoint_returns_200_when_degraded():
    r = _client([Check("db", _ok, required=True), Check("vlm", _boom, required=False)]).get("/api/v1/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "degraded"


def test_default_checks_cover_required_and_optional_dependencies():
    from e2eai.readiness_checks import default_checks

    by_name = {c.name: c.required for c in default_checks()}
    assert by_name == {"postgres": True, "valkey": True, "openfga": True, "model-gateway": False}
