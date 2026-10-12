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
