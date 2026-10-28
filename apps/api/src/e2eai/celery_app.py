"""Celery application: the P0 job engine (FR-F20, PRD T1/T2).

The broker is the existing Valkey (its own databases, apart from sessions). Tasks are plain JSON; file content
never travels through the broker: a task only carries the version id and reads the object from storage.
The app is built lazily so importing this module does not require a configured install.
"""

import logging
from functools import lru_cache

from celery import Celery

log = logging.getLogger("e2eai.celery")
TASK_TIME_LIMIT_SECONDS = 1800  # a large scanned PDF on CPU can take a while


@lru_cache
def get_celery_app() -> Celery:
    from .core.config import get_settings

    s = get_settings()
    app = Celery("e2eai", broker=s.celery_broker_url, backend=s.celery_result_url, include=["e2eai.jobs.ingest"])
    app.conf.update(
        task_serializer="json", result_serializer="json", accept_content=["json"],  # never pickle
        task_acks_late=True, worker_prefetch_multiplier=1,  # a crashed worker's task is redelivered, one at a time
        task_time_limit=TASK_TIME_LIMIT_SECONDS, task_track_started=True, result_expires=3600,
        broker_connection_retry_on_startup=True, broker_connection_timeout=3,
        broker_transport_options={"visibility_timeout": TASK_TIME_LIMIT_SECONDS + 300, "socket_connect_timeout": 3, "socket_timeout": 5},
        timezone="UTC", enable_utc=True,
    )
    return app


def worker_online(timeout: float = 1.0) -> bool:
    """True only when a worker answers a ping. Any broker problem counts as 'no worker' (callers fall back)."""
    try:
        return bool(get_celery_app().control.ping(timeout=timeout))
    except Exception as exc:  # noqa: BLE001 - broker down / misconfigured: never break an upload over a probe
        log.warning("celery worker probe failed: %s", type(exc).__name__)
        return False


def __getattr__(name: str):  # PEP 562: `from e2eai.celery_app import celery_app`
    if name == "celery_app":
        return get_celery_app()
    raise AttributeError(name)
