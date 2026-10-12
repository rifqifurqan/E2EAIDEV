"""NFR-18 / NFR-20 / NFR-16: API security headers, request id, and EN/ID problem details."""

import re

from fastapi.testclient import TestClient

from e2eai.main import create_app


def _client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


def test_security_headers_present_on_every_response():
    r = _client().get("/api/v1/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert "max-age=" in r.headers["strict-transport-security"]
    assert r.headers["cache-control"] == "no-store"


def test_request_id_is_generated_and_unique():
    c = _client()
    a = c.get("/api/v1/health").headers["x-request-id"]
    b = c.get("/api/v1/health").headers["x-request-id"]
    assert a != b
    assert re.fullmatch(r"[0-9a-f-]{36}", a)


def test_safe_client_request_id_is_echoed_and_unsafe_one_replaced():
    c = _client()
    ok = c.get("/api/v1/health", headers={"X-Request-ID": "trace-abc_123"})
    assert ok.headers["x-request-id"] == "trace-abc_123"
    bad = c.get("/api/v1/health", headers={"X-Request-ID": "x" * 200})
    assert bad.headers["x-request-id"] != "x" * 200
    assert re.fullmatch(r"[0-9a-f-]{36}", bad.headers["x-request-id"])


def test_problem_details_include_request_id_and_bilingual_title():
    r = _client().get("/api/v1/does-not-exist")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["request_id"] == r.headers["x-request-id"]
    assert body["title"] == "Not found"
    assert body["title_id"] == "Tidak ditemukan"


def test_validation_error_has_indonesian_title_and_no_internals():
    r = _client().post("/api/v1/auth/login", json={})
    assert r.status_code == 422
    body = r.json()
    assert body["title_id"] == "Permintaan tidak valid"
    assert "Traceback" not in r.text and "pydantic" not in r.text.lower()


def test_error_responses_also_get_security_headers():
    r = _client().get("/api/v1/does-not-exist")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-request-id"]
