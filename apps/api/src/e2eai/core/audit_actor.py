"""Who made the change (NFR-20 created_by / updated_by), filled in automatically.

The request layer sets the acting principal once (``set_actor``); a SQLAlchemy ``before_flush`` hook then stamps
``created_by`` on new rows and ``updated_by`` on rows with a real net change. Values that code sets explicitly are
never overwritten, and a no-op assignment does not stamp anything. Outside a request (workers, scripts, tests
without a scope) no actor is set and the columns stay NULL, which means "written by the system".
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy import event
from sqlalchemy.orm import Session

_ACTOR: ContextVar[str | None] = ContextVar("e2eai_actor", default=None)


def current_actor() -> str | None:
    return _ACTOR.get()


def set_actor(actor: str | None) -> None:
    _ACTOR.set(actor)


@contextmanager
def actor_scope(actor: str | None) -> Iterator[None]:
    token = _ACTOR.set(actor)
    try:
        yield
    finally:
        _ACTOR.reset(token)


def _has(obj, name: str) -> bool:
    return name in obj.__mapper__.column_attrs.keys()


@event.listens_for(Session, "before_flush")
def _stamp_actor(session: Session, flush_context, instances) -> None:
    actor = _ACTOR.get()
    if not actor:
        return
    for obj in session.new:
        if _has(obj, "created_by") and getattr(obj, "created_by", None) is None:
            obj.created_by = actor
    for obj in session.dirty:
        if _has(obj, "updated_by") and session.is_modified(obj, include_collections=False):
            # Only stamp when something other than the audit columns themselves changed.
            changed = {a.key for a in obj.__mapper__.column_attrs if session.is_modified(obj, include_collections=False)
                       and _attr_changed(obj, a.key)}
            if changed - {"updated_at", "updated_by"}:
                obj.updated_by = actor


def _attr_changed(obj, key: str) -> bool:
    from sqlalchemy import inspect

    return inspect(obj).attrs[key].history.has_changes()
