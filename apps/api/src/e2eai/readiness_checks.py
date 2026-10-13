"""Concrete readiness probes for the API (NFR-16, NFR-19). Required: Postgres, Valkey, OpenFGA (permission
checks fail closed without it). Optional: the model gateway (chat degrades with a clear error)."""

import httpx
from sqlalchemy import text

from .auth import redis_client
from .core.config import get_settings
from .core.readiness import Check
from .db import sessions


async def _db() -> None:
    async with sessions()() as session:
        await session.execute(text("SELECT 1"))


async def _valkey() -> None:
    await redis_client().ping()


async def _openfga() -> None:
    s = get_settings()
    async with httpx.AsyncClient(base_url=s.openfga_url, timeout=2.0) as c:
        (await c.get("/healthz")).raise_for_status()


async def _gateway() -> None:
    s = get_settings()
    async with httpx.AsyncClient(base_url=s.litellm_url, timeout=2.0) as c:
        (await c.get("/health/liveliness")).raise_for_status()


def default_checks() -> list[Check]:
    return [
        Check("postgres", _db, required=True),
        Check("valkey", _valkey, required=True),
        Check("openfga", _openfga, required=True),
        Check("model-gateway", _gateway, required=False),
    ]
