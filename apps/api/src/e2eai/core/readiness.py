"""Readiness checks (NFR-16, NFR-19).

Each dependency is a ``Check``. A failing *required* check (database, permission store, session store) makes the
service ``not_ready`` (HTTP 503) so an orchestrator stops routing traffic; a failing *optional* check (model
gateway, Langfuse, VLM) only marks the service ``degraded`` and chat stays up. The response lists check names and
``ok``/``unavailable`` only: never exception text, hosts, or credentials.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import APIRouter
from fastapi.responses import JSONResponse

DEFAULT_TIMEOUT = 2.0


@dataclass(frozen=True)
class Check:
    name: str
    probe: Callable[[], Awaitable[None]]
    required: bool = True


async def _one(check: Check, timeout: float) -> bool:
    try:
        await asyncio.wait_for(check.probe(), timeout)
        return True
    except Exception:  # noqa: BLE001 - any failure, including timeout, means unavailable
        return False


async def run_checks(checks: list[Check], timeout: float = DEFAULT_TIMEOUT) -> dict:
    outcomes = await asyncio.gather(*(_one(c, timeout) for c in checks))
    status = "ready"
    for check, ok in zip(checks, outcomes, strict=True):
        if ok:
            continue
        if check.required:
            status = "not_ready"
            break
        status = "degraded"
    return {
        "status": status,
        "checks": {c.name: ("ok" if ok else "unavailable") for c, ok in zip(checks, outcomes, strict=True)},
    }


def make_ready_router(get_checks: Callable[[], list[Check]], timeout: float = DEFAULT_TIMEOUT) -> APIRouter:
    router = APIRouter(tags=["ops"])

    @router.get("/api/v1/ready")
    async def ready() -> JSONResponse:
        result = await run_checks(get_checks(), timeout)
        return JSONResponse(result, status_code=503 if result["status"] == "not_ready" else 200)

    return router
