"""Opaque keyset (cursor) pagination helpers (NFR-20).

The cursor encodes the sort key of the last returned row: ``(timestamp, id)``. It carries no user data and is
not an authorization token; list queries must still apply their normal ownership/permission filters.
"""

import base64
import json
import uuid
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any, TypeVar

from .errors import AppError

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
T = TypeVar("T")


def clamp_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    return max(1, min(int(limit), MAX_LIMIT))


def encode_cursor(ts: datetime, row_id: uuid.UUID) -> str:
    raw = json.dumps({"t": ts.isoformat(), "i": str(row_id)}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        data: Any = json.loads(raw)
        return datetime.fromisoformat(data["t"]), uuid.UUID(data["i"])
    except Exception:
        raise AppError(422, "Invalid cursor", "The pagination cursor is not valid.", "invalid-cursor") from None


def make_page(rows: Sequence[T], limit: int, key: Callable[[T], tuple[datetime, uuid.UUID]]) -> tuple[list[T], str | None]:
    """``rows`` must be fetched with ``limit + 1`` rows; the extra row signals that another page exists."""
    items = list(rows[:limit])
    if len(rows) > limit and items:
        ts, row_id = key(items[-1])
        return items, encode_cursor(ts, row_id)
    return items, None
