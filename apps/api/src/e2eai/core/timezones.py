"""Display time zones (NFR-20): timestamps are stored in UTC and shown in the user's time zone.

The default is Asia/Jakarta. A stored zone that is no longer valid falls back to the default instead of
failing a request. Needs the ``tzdata`` package on platforms without a system zone database.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .errors import AppError

DEFAULT_TIME_ZONE = "Asia/Jakarta"
_MAX_LEN = 64


def _load(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or DEFAULT_TIME_ZONE)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return ZoneInfo(DEFAULT_TIME_ZONE)


def validate_time_zone(name: str) -> str:
    """Return ``name`` when it is a real IANA zone, else raise a 422 problem."""
    if isinstance(name, str) and 0 < len(name) <= _MAX_LEN and "/" in name and ".." not in name:
        try:
            ZoneInfo(name)
            return name
        except (ZoneInfoNotFoundError, ValueError, OSError):
            pass
    raise AppError(422, "Invalid time zone", "Use an IANA time zone name such as Asia/Jakarta.", "invalid-time-zone")


def to_user_time(moment: datetime, time_zone: str | None) -> datetime:
    """Convert a stored UTC timestamp (naive values are taken as UTC) to the user's zone."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(_load(time_zone))
