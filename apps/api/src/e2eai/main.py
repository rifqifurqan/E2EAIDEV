"""FastAPI application entrypoint for Phase 0 (PRD T1/T7)."""

from fastapi import FastAPI
from sqlalchemy import text

from .core.errors import install
from .db import sessions


def create_app() -> FastAPI:
    app = FastAPI(title="E2EAIDEV API", version="0.1.0")
    install(app)

    @app.get("/api/v1/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/ready", tags=["ops"])
    async def ready() -> dict[str, str]:
        async with sessions()() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ready"}

    return app


app = create_app()
