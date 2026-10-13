"""NFR-19: circuit breaker stops hammering a dead upstream and fails fast with a clear 503."""

import asyncio

import httpx
import pytest

from e2eai.core.errors import AppError
from e2eai.core.resilience import CircuitBreaker, CircuitOpen, post_json_with_retry, reset_breakers


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def test_opens_after_threshold_and_half_opens_after_cooldown():
    clock = Clock()
    cb = CircuitBreaker(failure_threshold=3, cooldown=10.0, clock=clock)
    for _ in range(2):
        cb.record_failure()
    assert cb.allow() is True  # still closed below the threshold
    cb.record_failure()
    assert cb.state == "open" and cb.allow() is False
    clock.t += 10.0
    assert cb.allow() is True and cb.state == "half_open"  # one probe allowed
    assert cb.allow() is False  # only a single probe at a time
    cb.record_success()
    assert cb.state == "closed" and cb.allow() is True


def test_failed_probe_reopens_and_success_resets_counter():
    clock = Clock()
    cb = CircuitBreaker(failure_threshold=2, cooldown=5.0, clock=clock)
    cb.record_failure()
    cb.record_success()  # resets consecutive failures
    cb.record_failure()
    assert cb.state == "closed"
    cb.record_failure()
    assert cb.state == "open"
    clock.t += 5.0
    assert cb.allow() is True
    cb.record_failure()
    assert cb.state == "open" and cb.allow() is False


class Resp:
    status_code = 200

    def json(self):
        return {}


def _factory(outcomes, calls):
    class Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, path, headers=None, json=None):
            calls["n"] += 1
            item = outcomes[min(calls["n"] - 1, len(outcomes) - 1)]
            if isinstance(item, BaseException):
                raise item
            return item

    return Client


async def _nosleep(d):
    pass


def _run(factory, breaker):
    return asyncio.run(post_json_with_retry(
        factory, base_url="http://dead", timeout=1.0, path="/p", headers={"Authorization": "Bearer s3cret-token"},
        json={}, attempts=1, sleep=_nosleep, breaker=breaker))


def test_open_breaker_fails_fast_without_calling_upstream():
    reset_breakers()
    calls = {"n": 0}
    factory = _factory([httpx.ConnectError("refused")], calls)
    cb = CircuitBreaker(failure_threshold=2, cooldown=60.0)
    for _ in range(2):
        with pytest.raises(AppError):
            _run(factory, cb)
    assert calls["n"] == 2
    with pytest.raises(AppError) as exc:
        _run(factory, cb)
    assert exc.value.status == 503 and exc.value.headers.get("Retry-After")
    assert calls["n"] == 2  # breaker open: upstream not contacted
    assert "s3cret-token" not in str(exc.value)


def test_success_closes_breaker_and_client_errors_do_not_trip_it():
    reset_breakers()
    calls = {"n": 0}
    ok = _factory([Resp()], calls)
    cb = CircuitBreaker(failure_threshold=1, cooldown=60.0)
    _run(ok, cb)
    assert cb.state == "closed"
    # A 4xx response is returned unchanged and is not an upstream outage.
    class Bad(Resp):
        status_code = 400

    calls2 = {"n": 0}
    _run(_factory([Bad()], calls2), cb)
    assert cb.state == "closed"


def test_circuit_open_is_distinct_exception():
    assert issubclass(CircuitOpen, Exception)


def test_breaker_state_is_exposed_in_prometheus_without_urls():
    from e2eai.core.metrics import MetricsRegistry, render_prometheus
    from e2eai.core.resilience import breaker_for

    reset_breakers()
    cb = breaker_for("http://user:pw@gateway.internal:4000/v1/embeddings", name="embeddings")
    for _ in range(cb.failure_threshold):
        cb.record_failure()
    breaker_for("http://gateway.internal:4000/rerank", name="rerank")
    text = render_prometheus(MetricsRegistry())
    assert 'circuit_breaker_state{upstream="embeddings"} 2' in text
    assert 'circuit_breaker_state{upstream="rerank"} 0' in text
    assert "gateway.internal" not in text and "pw@" not in text
    reset_breakers()
