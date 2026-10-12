"""Admin-only Prometheus scrape endpoint for request metrics (NFR-16)."""

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import current_session, require_scope
from .core.errors import AppError
from .core.metrics import render_prometheus
from .db import User, get_session
from .legal_hold import is_admin

router = APIRouter(prefix="/api/v1", tags=["ops"])


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics_api(sess: dict = Depends(current_session), db: AsyncSession = Depends(get_session)) -> PlainTextResponse:
    require_scope(sess, "evals")
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None or user.status != "active":
        raise AppError(401, "Not authenticated")
    if not await is_admin(db, user):
        raise AppError(403, "Not allowed")
    return PlainTextResponse(render_prometheus(), media_type="text/plain; version=0.0.4")
