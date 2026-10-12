"""Credential redaction for log output (NFR-7: no plaintext credentials in logs).

A ``logging.Filter`` rewrites the formatted message (and drops raw args) so secrets passed via format args,
DSNs, bearer tokens, cookies, or ``key=value`` pairs never reach a handler. Pure regex, no I/O.
"""

import logging
import re

MASK = "[REDACTED]"

_PATTERNS: list[re.Pattern[str]] = [
    # scheme://user:password@host
    re.compile(r"(?P<pre>[A-Za-z][A-Za-z0-9+.\-]*://[^\s:/@]+:)(?P<val>[^\s@/]+)(?=@)"),
    # Authorization: Bearer xxx / Basic xxx
    re.compile(r"(?i)(?P<pre>\b(?:bearer|basic)\s+)(?P<val>[A-Za-z0-9._~+/=\-]{6,})"),
    # sk-... style provider keys
    re.compile(r"(?P<pre>)(?P<val>\bsk-[A-Za-z0-9_\-]{8,})"),
    # JSON / key=value / header style: password, secret, token, api key, session, cookie values
    re.compile(
        r"(?i)(?P<pre>[\"']?\b(?:password|passwd|pwd|secret|token|api[_-]?key|x-api-key|apikey|credential|"
        r"session|e2eai_session|access[_-]?key|private[_-]?key)[\"']?\s*[=:]\s*[\"']?)(?P<val>[^\s\"',;&]+)"
    ),
]


def redact_secrets(text: str) -> str:
    for pat in _PATTERNS:
        text = pat.sub(lambda m: f"{m.group('pre')}{MASK}", text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            message = str(record.msg)
        record.msg = redact_secrets(message)
        record.args = None
        return True


def install_log_redaction() -> None:
    """Attach the filter to the root logger's handlers and to the root logger (idempotent)."""
    root = logging.getLogger()
    if not any(isinstance(f, RedactingFilter) for f in root.filters):
        root.addFilter(RedactingFilter())
    for handler in root.handlers:
        if not any(isinstance(f, RedactingFilter) for f in handler.filters):
            handler.addFilter(RedactingFilter())
    for name in ("e2eai", "uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        if not any(isinstance(f, RedactingFilter) for f in lg.filters):
            lg.addFilter(RedactingFilter())
