"""NFR-16: request metrics (Prometheus text) with low-cardinality labels and no user data."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from e2eai.core.metrics import MetricsMiddleware, MetricsRegistry, render_prometheus


def _app(reg):
    app = FastAPI()

    @app.get("/items/{item_id}")
    async def item(item_id: str):
        return {"id": item_id}

    @app.get("/fail")
    async def fail():
        raise RuntimeError("boom")

    app.add_middleware(MetricsMiddleware, registry=reg)
    return TestClient(app, raise_server_exceptions=False)


def test_counts_use_route_template_not_raw_path():
    reg = MetricsRegistry()
    c = _app(reg)
    c.get("/items/alice@example.com")
    c.get("/items/42")
    text = render_prometheus(reg)
    assert 'http_requests_total{method="GET",route="/items/{item_id}",status="200"} 2' in text
    assert "alice" not in text and "42" not in text


def test_unmatched_paths_collapse_into_one_label():
    reg = MetricsRegistry()
    c = _app(reg)
    c.get("/nope/1")
    c.get("/nope/2")
    text = render_prometheus(reg)
    assert 'route="unmatched",status="404"} 2' in text


def test_server_errors_are_counted_as_500():
    reg = MetricsRegistry()
    _app(reg).get("/fail")
    assert 'route="/fail",status="500"} 1' in render_prometheus(reg)


def test_latency_histogram_has_cumulative_buckets_sum_and_count():
    reg = MetricsRegistry()
    reg.observe("GET", "/x", 200, 0.03)
    reg.observe("GET", "/x", 200, 0.7)
    text = render_prometheus(reg)
    assert 'http_request_duration_seconds_bucket{method="GET",route="/x",le="0.05"} 1' in text
    assert 'http_request_duration_seconds_bucket{method="GET",route="/x",le="1"} 2' in text
    assert 'http_request_duration_seconds_bucket{method="GET",route="/x",le="+Inf"} 2' in text
    assert 'http_request_duration_seconds_count{method="GET",route="/x"} 2' in text
    assert 'http_request_duration_seconds_sum{method="GET",route="/x"} 0.73' in text


def test_metrics_endpoint_requires_an_authenticated_admin_session():
    from e2eai.main import create_app

    c = TestClient(create_app(), raise_server_exceptions=False)
    r = c.get("/api/v1/metrics")
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")
    assert "http_requests_total" not in r.text


def test_metrics_endpoint_serves_prometheus_text_for_admin_and_denies_non_admin(monkeypatch):
    import uuid

    from e2eai.auth import current_session
    from e2eai.db import get_session
    from e2eai.main import create_app

    class FakeUser:
        id = uuid.uuid4()
        status = "active"

    class FakeDb:
        async def get(self, model, key):
            return FakeUser()

    app = create_app()
    state = {"admin": True}

    async def fake_session():
        return {"user_id": str(FakeUser.id), "auth_type": "session", "csrf": "x"}

    async def fake_db():
        yield FakeDb()

    app.dependency_overrides[current_session] = fake_session
    app.dependency_overrides[get_session] = fake_db

    import e2eai.metrics_api as api

    async def fake_is_admin(db, user):
        return state["admin"]

    monkeypatch.setattr(api, "is_admin", fake_is_admin)
    c = TestClient(app, raise_server_exceptions=False)
    c.get("/api/v1/health")
    r = c.get("/api/v1/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert 'route="/api/v1/health"' in r.text
    assert r.headers["x-content-type-options"] == "nosniff"
    state["admin"] = False
    assert c.get("/api/v1/metrics").status_code == 403
