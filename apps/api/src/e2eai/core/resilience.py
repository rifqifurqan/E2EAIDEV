"""Timeout + bounded retry with exponential backoff for external calls (NFR-19).

``with_retry`` applies a per-attempt timeout and retries only transient errors. The final error is wrapped in
``RetryExhausted`` with credentials redacted, so callers can degrade or surface a clear message.
"""

import asyncio
import random
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


RETRY_STATUS = frozenset({429, 502, 503, 504})


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
):
    """POST with bounded retries on transport errors and 429/502/503/504 (NFR-19).

    Other statuses (including 4xx) are returned to the caller unchanged. When retries are exhausted a clear
    503 ``AppError`` is raised; neither headers nor payload appear in its message.
    """
    from .errors import AppError

    async def once():
        async with client_factory(base_url=base_url, timeout=timeout) as client:
            response = await client.post(path, headers=headers, json=json)
        status = getattr(response, "status_code", 200)  # test fakes may omit it
        if status in RETRY_STATUS:
            raise _RetryableStatus(status)
        return response

    retryable = TRANSIENT + (_RetryableStatus,) + _httpx_transient()
    try:
        return await with_retry(once, attempts=attempts, timeout=None, retry_on=retryable, sleep=sleep)
    except RetryExhausted:
        raise AppError(503, "Upstream service unavailable",
                       "A model or search service did not respond. Please try again shortly.",
                       "upstream-unavailable") from None


def _httpx_transient() -> tuple[type[BaseException], ...]:
    import httpx

    return (httpx.TransportError,)
