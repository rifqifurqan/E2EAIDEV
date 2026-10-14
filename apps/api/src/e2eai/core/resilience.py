"""Timeout + bounded retry with exponential backoff for external calls (NFR-19).

``with_retry`` applies a per-attempt timeout and retries only transient errors. The final error is wrapped in
``RetryExhausted`` with credentials redacted, so callers can degrade or surface a clear message.
"""

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

from .log_redaction import redact_secrets

T = TypeVar("T")
TRANSIENT: tuple[type[BaseException], ...] = (ConnectionError, TimeoutError, asyncio.TimeoutError, OSError)


class RetryExhausted(Exception):
    def __init__(self, attempts: int, last: BaseException):
        self.attempts = attempts
        self.last_type = type(last).__name__
        super().__init__(f"Operation failed after {attempts} attempts ({self.last_type}): {redact_secrets(str(last))}")


async def with_retry(
    fn: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 0.2,
    max_delay: float = 5.0,
    timeout: float | None = 10.0,
    retry_on: tuple[type[BaseException], ...] = TRANSIENT,
    jitter: float = 0.1,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    attempts = max(1, attempts)
    last: BaseException | None = None
    for i in range(attempts):
        try:
            if timeout is None:
                return await fn()
            return await asyncio.wait_for(fn(), timeout)
        except retry_on as exc:
            last = exc
            if i == attempts - 1:
                break
            delay = min(max_delay, base_delay * (2 ** i))
            await sleep(delay + (random.uniform(0, jitter) if jitter else 0.0))
    assert last is not None
    raise RetryExhausted(attempts, last)


class CircuitOpen(Exception):
    """Raised when the breaker is open and the upstream must not be contacted."""


class CircuitBreaker:
    """Consecutive-failure circuit breaker: closed -> open -> half_open (one probe) -> closed (NFR-19)."""

    def __init__(self, failure_threshold: int = 5, cooldown: float = 30.0, clock: Callable[[], float] = time.monotonic):
        self.failure_threshold = max(1, failure_threshold)
        self.cooldown = cooldown
        self._clock = clock
        self.state = "closed"
        self._failures = 0
        self._opened_at = 0.0

    def allow(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open" and self._clock() - self._opened_at >= self.cooldown:
            self.state = "half_open"  # allow exactly one probe
            return True
        return False

    def retry_after(self) -> int:
        remaining = self.cooldown - (self._clock() - self._opened_at)
        return max(1, int(remaining + 0.999)) if self.state == "open" else 1

    def record_success(self) -> None:
        self.state = "closed"
        self._failures = 0

    def record_failure(self) -> None:
        self._failures += 1
        if self.state == "half_open" or self._failures >= self.failure_threshold:
            self.state = "open"
            self._opened_at = self._clock()


_BREAKERS: dict[str, CircuitBreaker] = {}


_NAMES: dict[str, str] = {}
STATE_VALUE = {"closed": 0, "half_open": 1, "open": 2}


def breaker_for(key: str, name: str | None = None) -> CircuitBreaker:
    """Shared per-upstream breaker. ``name`` is the short, URL-free label used in metrics."""
    if name:
        _NAMES[key] = name
    return _BREAKERS.setdefault(key, CircuitBreaker())


def breaker_states() -> dict[str, int]:
    """Metric view: upstream label -> 0 closed / 1 half_open / 2 open. Labels never contain URLs."""
    out: dict[str, int] = {}
    for key, cb in _BREAKERS.items():
        label = _NAMES.get(key, "unnamed")
        out[label] = max(out.get(label, 0), STATE_VALUE[cb.state])
    return out


def reset_breakers() -> None:
    _BREAKERS.clear()
    _NAMES.clear()


# 500 included: LiteLLM answers 500 while a local model runner reloads or crashes (seen in live UAT); the call is idempotent.
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


class _RetryableStatus(Exception):
    def __init__(self, status: int):
        super().__init__(f"upstream status {status}")
        self.status = status


async def post_json_with_retry(
    client_factory,
    *,
    base_url: str,
    timeout: float,
    path: str,
    headers: dict,
    json: dict,
    attempts: int = 3,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    breaker: CircuitBreaker | None = None,
):
    """POST with bounded retries on transport errors and 429/502/503/504 (NFR-19).

    Other statuses (including 4xx) are returned to the caller unchanged. When retries are exhausted a clear
    503 ``AppError`` is raised; neither headers nor payload appear in its message.
    """
    from .errors import AppError

    if breaker is not None and not breaker.allow():
        raise AppError(503, "Upstream service unavailable",
                       "A model or search service is temporarily unavailable. Please try again shortly.",
                       "upstream-unavailable", headers={"Retry-After": str(breaker.retry_after())})

    async def once():
        async with client_factory(base_url=base_url, timeout=timeout) as client:
            response = await client.post(path, headers=headers, json=json)
        status = getattr(response, "status_code", 200)  # test fakes may omit it
        if status in RETRY_STATUS:
            raise _RetryableStatus(status)
        return response

    retryable = TRANSIENT + (_RetryableStatus,) + _httpx_transient()
    try:
        result = await with_retry(once, attempts=attempts, timeout=None, retry_on=retryable, sleep=sleep)
        if breaker is not None:
            breaker.record_success()
        return result
    except RetryExhausted:
        if breaker is not None:
            breaker.record_failure()
        raise AppError(503, "Upstream service unavailable",
                       "A model or search service did not respond. Please try again shortly.",
                       "upstream-unavailable") from None


def _httpx_transient() -> tuple[type[BaseException], ...]:
    import httpx

    return (httpx.TransportError,)
