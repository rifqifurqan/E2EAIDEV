"""Write-action confirmation flow for MCP tool calls (FR-X5).

Read-only tools execute immediately. Write/mutating tools (needs_confirmation=True)
are initially skipped (status=skipped_confirmation) and require explicit user
confirmation before execution.

This module provides:
- ``confirm_tool_call``: confirm or deny a pending write action
- API route for user confirmation

Only safe metadata is stored and audited: operation_id, system_id, confirming
user, decision. Raw tokens, credentials, payloads, and server URLs are never
stored or returned.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .auth import current_session, require_scope
from .core.errors import AppError
from .db import McpToolCall, User, get_session
from .mcp_tool_call import Executor, MCPToolCallRecord, OfflineExecutor, sanitize_mcp_safe_result


# ---------------------------------------------------------------------------
# Service helper
# ---------------------------------------------------------------------------


async def confirm_tool_call(
    session: AsyncSession,
    *,
    tool_call_id: uuid.UUID,
    user: User,
    decision: str,
    executor: Executor | None = None,
) -> dict:
    """Confirm or deny a pending (skipped_confirmation) write action.

    ``decision`` must be "confirm" or "deny".
    - "confirm": execute the tool call offline, persist the safe result, and audit.
    - "deny": mark the tool call as denied and audit.

    Only safe metadata is stored. Raw tokens, credentials, and payloads are never persisted.
    """
    if decision not in ("confirm", "deny"):
        raise AppError(400, "Invalid decision", "Use 'confirm' or 'deny'.")

    tc = await session.get(McpToolCall, tool_call_id)
    if tc is None:
        raise AppError(404, "Tool call not found")

    if tc.status != "skipped_confirmation":
        raise AppError(409, "Tool call is not pending confirmation",
                       f"Current status: {tc.status}")

    if decision == "deny":
        tc.status = "denied"
        await audit.record(
            session, f"user:{user.id}", "mcp.tool_call.denied",
            f"system:{tc.system_id}:{tc.operation_id}",
            {
                "operation_id": tc.operation_id,
                "system_id": tc.system_id,
                "denied_by": str(user.id),
            },
        )
        await session.commit()
        return {"status": "denied", "operation_id": tc.operation_id}

    # decision == "confirm"
    _executor = executor if executor is not None else OfflineExecutor()

    record = MCPToolCallRecord(
        system_id=tc.system_id,
        operation_id=tc.operation_id,
        method=tc.method,
        path=tc.path,
        read_only=tc.read_only,
        needs_confirmation=tc.needs_confirmation,
        tool_description="",
        match_score=0.0,
    )

    safe = sanitize_mcp_safe_result(await _executor.execute(record))
    tc.status = "confirmed_executed"
    tc.safe_result = safe

    await audit.record(
        session, f"user:{user.id}", "mcp.tool_call.confirmed",
        f"system:{tc.system_id}:{tc.operation_id}",
        {
            "operation_id": tc.operation_id,
            "system_id": tc.system_id,
            "confirmed_by": str(user.id),
            "method": tc.method,
        },
    )
    await session.commit()
    return {"status": "confirmed_executed", "operation_id": tc.operation_id}


# ---------------------------------------------------------------------------
# FastAPI route
# ---------------------------------------------------------------------------


class ConfirmIn(BaseModel):
    decision: str  # "confirm" | "deny"


router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat/tool-calls/{tool_call_id}/confirm")
async def confirm_tool_call_api(
    tool_call_id: uuid.UUID,
    body: ConfirmIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """FR-X5: Confirm or deny a pending write action.

    Only safe metadata is returned. Raw tokens, credentials, and payloads are never included.
    """
    require_scope(sess, "chat")
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None:
        raise AppError(401, "Not authenticated")
    return await confirm_tool_call(
        db, tool_call_id=tool_call_id, user=user, decision=body.decision,
    )
