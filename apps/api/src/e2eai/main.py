"""FastAPI application entrypoint for Phase 0 (PRD T1/T7)."""

from fastapi import FastAPI
from sqlalchemy import text

from .auth import router as auth_router
from .documents import router as documents_router
from .retrieval import router as retrieval_router
from .core.errors import install
from .db import sessions


def create_app() -> FastAPI:
    app = FastAPI(title="E2EAIDEV API", version="0.1.0")
    install(app)
    app.include_router(auth_router)
    app.include_router(documents_router)
    app.include_router(retrieval_router)

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
