"""NFR-7: no plaintext credentials in logs. NFR-19: bounded retry with backoff for external calls."""

import asyncio
import logging

import pytest

from e2eai.core.log_redaction import RedactingFilter, install_log_redaction, redact_secrets
from e2eai.core.resilience import RetryExhausted, with_retry


@pytest.mark.parametrize("raw,leak", [
    ("login password=hunter2secret ok", "hunter2secret"),
    ("Authorization: Bearer abc.DEF-123_xyz", "abc.DEF-123_xyz"),
    ("call failed key sk-LIVEABCDEF123456 here", "sk-LIVEABCDEF123456"),
    ("postgresql+asyncpg://user:p4ssw0rd-long@db:5432/x", "p4ssw0rd-long"),
    ("cookie: e2eai_session=abcdef0123456789; Path=/", "abcdef0123456789"),
    ('{"api_key": "AKIA-very-secret-1234"}', "AKIA-very-secret-1234"),
    ("X-API-Key: master-key-0123456789", "master-key-0123456789"),
])
def test_redact_secrets_removes_credentials(raw, leak):
    out = redact_secrets(raw)
    assert leak not in out
    assert "[REDACTED]" in out


def test_redact_secrets_keeps_ordinary_text():
    s = "document 42 indexed in 31 ms for user andi"
    assert redact_secrets(s) == s


def test_logging_filter_redacts_message_and_args():
    rec = logging.LogRecord("x", logging.INFO, __file__, 1, "token=%s done", ("supersecretvalue1",), None)
    assert RedactingFilter().filter(rec) is True
    assert "supersecretvalue1" not in rec.getMessage()


def test_installed_filter_applies_to_real_logger_output(caplog):
    install_log_redaction()
    log = logging.getLogger("e2eai.test_nfr7")
    with caplog.at_level(logging.INFO):
        log.info("connect dsn=postgresql://u:pw-very-secret@h/db password=%s", "another-secret-9")
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "pw-very-secret" not in text and "another-secret-9" not in text


def test_with_retry_retries_transient_then_succeeds_without_real_sleep():
    delays, calls = [], {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("down")
        return "ok"

    async def fake_sleep(d):
        delays.append(d)

    out = asyncio.run(with_retry(flaky, attempts=4, base_delay=0.1, sleep=fake_sleep, jitter=0))
    assert out == "ok" and calls["n"] == 3
    assert delays == [0.1, 0.2]  # exponential backoff


def test_with_retry_does_not_retry_non_retryable_errors():
    calls = {"n": 0}

    async def bad():
        calls["n"] += 1
        raise ValueError("bad input")

    with pytest.raises(ValueError):
        asyncio.run(with_retry(bad, attempts=4, retry_on=(ConnectionError, TimeoutError)))
    assert calls["n"] == 1


def test_with_retry_gives_up_after_attempts_with_safe_error():
    async def down():
        raise ConnectionError("password=hunter2secret refused")

    async def nosleep(d):
        pass

    with pytest.raises(RetryExhausted) as e:
        asyncio.run(with_retry(down, attempts=3, sleep=nosleep, jitter=0))
    assert e.value.attempts == 3
    assert "hunter2secret" not in str(e.value)


def test_with_retry_enforces_per_attempt_timeout():
    async def slow():
        await asyncio.sleep(5)

    async def nosleep(d):
        pass

    with pytest.raises(RetryExhausted):
        asyncio.run(with_retry(slow, attempts=2, timeout=0.05, sleep=nosleep, jitter=0))


# --- uvicorn's access formatter reads record.args as a 5-tuple: the filter must not break it -----------------------

def _access_record(path: str) -> logging.LogRecord:
    return logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
                             ("127.0.0.1:5000", "GET", path, "1.1", 200), None)


def test_a_clean_access_log_line_keeps_its_args_so_uvicorn_can_format_it():
    from uvicorn.logging import AccessFormatter

    record = _access_record("/api/v1/health")
    assert RedactingFilter().filter(record) is True
    assert record.args == ("127.0.0.1:5000", "GET", "/api/v1/health", "1.1", 200)
    assert "GET /api/v1/health HTTP/1.1" in AccessFormatter(use_colors=False).format(record)  # used to raise


def test_a_secret_in_the_request_path_is_redacted_without_breaking_the_five_tuple():
    from uvicorn.logging import AccessFormatter

    record = _access_record("/auth/oidc/callback?code=1&token=SUPERSECRETVALUE123")
    RedactingFilter().filter(record)
    assert isinstance(record.args, tuple) and len(record.args) == 5
    out = AccessFormatter(use_colors=False).format(record)
    assert "SUPERSECRETVALUE123" not in out and "[REDACTED]" in out


def test_other_loggers_with_secrets_are_still_rendered_and_redacted():
    record = logging.LogRecord("e2eai", logging.INFO, __file__, 1, "connect password=%s ok", ("hunter2secret",), None)
    RedactingFilter().filter(record)
    assert "hunter2secret" not in record.getMessage() and record.args is None
