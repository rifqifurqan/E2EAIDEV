"""Question-time MCP tool-call planner and no-vectorize guard (FR-X2).

At question time the system selects relevant MCP tools from registered
descriptors and plans calls. Live tool results are NEVER copied into
vectors, embeddings, or the chunk index.

Delegated identity (FR-X3) and actual network execution are future slices;
this module plans and records tool calls deterministically/offline.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Protocol

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .auth import current_session, require_scope
from .db import get_session
from .mcp_gen import MCPServerDescriptor, MCPToolDescriptor


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MCPToolCallRecord:
    """Safe record of a planned MCP tool call. No auth secrets, no raw payloads."""

    system_id: str
    operation_id: str
    method: str
    path: str
    read_only: bool
    needs_confirmation: bool
    tool_description: str
    match_score: float


@dataclass(frozen=True)
class LiveToolResult:
    """Marker for data that came from a live MCP tool call.

    ``vectorizable`` is always False — live tool results must never be
    copied into the vector store (FR-X2 core invariant).
    """

    system_id: str
    operation_id: str
    source: str  # always "live_mcp"
    vectorizable: bool = field(default=False, init=False)


# ---------------------------------------------------------------------------
# No-vectorize guard
# ---------------------------------------------------------------------------


def reject_vectorize_live_result(result: LiveToolResult) -> None:
    """Raise if anyone attempts to vectorize/embed/index a live tool result.

    This is the FR-X2 core invariant: live system data stays ephemeral
    and is never copied into the chunk/embedding store.
    """
    if result.source == "live_mcp" or not result.vectorizable:
        raise ValueError(
            "Live tool result must not be vectorized, indexed, or embedded. "
            "FR-X2: live system data is fetched at question time only."
        )


# ---------------------------------------------------------------------------
# Keyword-based relevance scoring (deterministic, offline)
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    """Extract lowercase alphanumeric tokens."""
    return set(_WORD_RE.findall(text.lower()))


def _relevance_score(question_tokens: set[str], tool: MCPToolDescriptor) -> float:
    """Score a tool's relevance to a question by token overlap.

    Combines the tool's name, description, and path. Returns 0.0–1.0.
    """
    tool_text = f"{tool.name} {tool.description} {tool.path}"
    tool_tokens = _tokenize(tool_text)
    if not tool_tokens or not question_tokens:
        return 0.0
    overlap = question_tokens & tool_tokens
    return len(overlap) / len(tool_tokens)


_RELEVANCE_THRESHOLD = 0.15


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------


def plan_mcp_tool_calls(
    *,
    descriptors: list[MCPServerDescriptor],
    question: str,
    threshold: float = _RELEVANCE_THRESHOLD,
) -> list[MCPToolCallRecord]:
    """Plan which MCP tools to call for a given question (FR-X2).

    Deterministic, offline keyword matching against tool metadata.
    Returns a list of MCPToolCallRecord sorted by relevance (highest first).
    Mutating tools (read_only=False) are flagged needs_confirmation=True (FR-X5).

    No network calls, no auth secrets, no raw payloads in the output.
    """
    if not descriptors or not question.strip():
        return []

    q_tokens = _tokenize(question)
    if not q_tokens:
        return []

    scored: list[tuple[float, MCPServerDescriptor, MCPToolDescriptor]] = []
    for desc in descriptors:
        for tool in desc.tools:
            score = _relevance_score(q_tokens, tool)
            if score >= threshold:
                scored.append((score, desc, tool))

    scored.sort(key=lambda t: t[0], reverse=True)

    return [
        MCPToolCallRecord(
            system_id=desc.system_id,
            operation_id=tool.operation_id,
            method=tool.method,
            path=tool.path,
            read_only=tool.read_only,
            needs_confirmation=not tool.read_only,
            tool_description=tool.description,
            match_score=round(score, 4),
        )
        for score, desc, tool in scored
    ]


def build_mcp_tool_plan_response(*, descriptors: list[MCPServerDescriptor], question: str) -> dict:
    """Build a safe API response for question-time MCP tool-call planning.

    The raw user question can contain secrets or sensitive business data, so it
    is used only for in-memory matching and is never echoed in the response.
    """
    records = plan_mcp_tool_calls(descriptors=descriptors, question=question)
    return {
        "planned_calls": [
            {
                "system_id": r.system_id,
                "operation_id": r.operation_id,
                "method": r.method,
                "path": r.path,
                "read_only": r.read_only,
                "needs_confirmation": r.needs_confirmation,
                "tool_description": r.tool_description,
                "match_score": r.match_score,
            }
            for r in records
        ],
        "total": len(records),
    }


# ---------------------------------------------------------------------------
# Executor protocol and offline boundary (no real MCP network calls in tests)
# ---------------------------------------------------------------------------


class Executor(Protocol):
    """Execute a planned MCP tool call and return a safe result summary."""

    async def execute(self, record: MCPToolCallRecord) -> dict: ...


class OfflineExecutor:
    """Deterministic offline executor — never makes real MCP network calls.

    Used in tests and as a safe default until FR-X3 delegated identity lands.
    Inject ``results`` to pre-configure per-operation-id return values.
    """

    def __init__(self, results: dict[str, dict] | None = None) -> None:
        self._results: dict[str, dict] = results or {}

    async def execute(self, record: MCPToolCallRecord) -> dict:
        base: dict = {"status": "offline", "record_count": 0}
        return {**base, **self._results.get(record.operation_id, {})}


_DANGEROUS_RESULT_KEY_PARTS = (
    "authorization",
    "bearer",
    "credential",
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "server_url",
    "base_url",
    "url",
    "uri",
    "payload",
    "request",
    "response",
    "raw",
    "question",
)


def _looks_sensitive_value(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in ("bearer ", "api-key", "api_key", "secret", "token", "http://", "https://"))


def sanitize_mcp_safe_result(value):
    """Return a secret-safe JSON-compatible result summary for persistence.

    Executors are allowed to return only summaries, but this guard strips common
    raw payload/auth/server fields defensively before DB persistence or response
    construction. Non-sensitive counts/status flags are preserved.
    """
    if isinstance(value, dict):
        safe: dict = {}
        for key, item in value.items():
            key_text = str(key).lower().replace("-", "_")
            if any(part in key_text for part in _DANGEROUS_RESULT_KEY_PARTS):
                continue
            safe[key] = sanitize_mcp_safe_result(item)
        return safe
    if isinstance(value, list):
        return [sanitize_mcp_safe_result(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_mcp_safe_result(item) for item in value]
    if isinstance(value, str):
        return "[REDACTED]" if _looks_sensitive_value(value) else value
    if value is None or isinstance(value, bool | int | float):
        return value
    return str(value)


def _identity_metadata(executor) -> tuple[str | None, str | None]:
    """Extract safe identity metadata from an executor if it carries delegated identity (FR-X3).

    Returns (auth_mode, acting_user_id) — both None if the executor has no identity context.
    Never returns raw tokens, bearer values, API keys, or secrets.
    """
    identity = getattr(executor, "identity", None)
    if identity is None:
        return None, None
    return getattr(identity, "auth_mode", None) and identity.auth_mode.value, identity.user_id


async def execute_and_persist_tool_calls(
    session: AsyncSession,
    *,
    records: list[MCPToolCallRecord],
    executor: Executor,
    message_id: uuid.UUID,
    actor: str,
) -> list[dict]:
    """Execute planned tool calls offline, persist safe records, and audit each.

    Mutating tools (needs_confirmation=True) are skipped — FR-X5 confirmation flow is not yet
    implemented. Only safe metadata is stored: never raw question text, auth secrets, server URLs,
    bearer tokens, API keys, or request/response payloads.

    FR-X3: if the executor carries a DelegatedIdentityContext (via ``identity`` property), its
    auth_mode and acting_user_id are persisted in the McpToolCall row and audit record. If the
    executor raises ValueError (e.g. SERVICE_ACCOUNT rejected), the tool call is recorded as
    ``rejected_service_account`` and the request is not aborted — fail safe, not fail open.
    """
    from .db import McpToolCall

    auth_mode, acting_user_id = _identity_metadata(executor)
    identity_audit = {}
    if auth_mode:
        identity_audit["auth_mode"] = auth_mode
    if acting_user_id:
        identity_audit["acting_user_id"] = acting_user_id

    summaries: list[dict] = []
    for r in records:
        if r.needs_confirmation:
            session.add(McpToolCall(
                message_id=message_id,
                system_id=r.system_id,
                operation_id=r.operation_id,
                method=r.method,
                path=r.path,
                read_only=r.read_only,
                needs_confirmation=True,
                status="skipped_confirmation",
                safe_result={"reason": "needs_confirmation"},
                auth_mode=auth_mode,
                acting_user_id=acting_user_id,
            ))
            await audit.record(
                session, actor, "mcp.tool_call.skipped",
                f"system:{r.system_id}:{r.operation_id}",
                {"read_only": r.read_only, "needs_confirmation": True, **identity_audit},
            )
            summaries.append({
                "system_id": r.system_id,
                "operation_id": r.operation_id,
                "status": "skipped_confirmation",
            })
        else:
            try:
                safe = sanitize_mcp_safe_result(await executor.execute(r))
                session.add(McpToolCall(
                    message_id=message_id,
                    system_id=r.system_id,
                    operation_id=r.operation_id,
                    method=r.method,
                    path=r.path,
                    read_only=r.read_only,
                    needs_confirmation=False,
                    status="executed",
                    safe_result=safe,
                    auth_mode=auth_mode,
                    acting_user_id=acting_user_id,
                ))
                await audit.record(
                    session, actor, "mcp.tool_call.executed",
                    f"system:{r.system_id}:{r.operation_id}",
                    {"read_only": r.read_only, "status": "executed", **identity_audit},
                )
                summaries.append({
                    "system_id": r.system_id,
                    "operation_id": r.operation_id,
                    "status": "executed",
                    "safe_result": safe,
                })
            except ValueError:
                # FR-X3: SERVICE_ACCOUNT or missing user_id — record rejection, don't abort
                session.add(McpToolCall(
                    message_id=message_id,
                    system_id=r.system_id,
                    operation_id=r.operation_id,
                    method=r.method,
                    path=r.path,
                    read_only=r.read_only,
                    needs_confirmation=False,
                    status="rejected_service_account",
                    safe_result={"reason": "service_account_not_allowed"},
                    auth_mode=auth_mode,
                    acting_user_id=acting_user_id,
                ))
                await audit.record(
                    session, actor, "mcp.tool_call.rejected",
                    f"system:{r.system_id}:{r.operation_id}",
                    {"read_only": r.read_only, "status": "rejected_service_account", **identity_audit},
                )
                summaries.append({
                    "system_id": r.system_id,
                    "operation_id": r.operation_id,
                    "status": "rejected_service_account",
                })
    return summaries


# ---------------------------------------------------------------------------
# FastAPI route (FR-X2)
# ---------------------------------------------------------------------------


class McpToolPlanIn(BaseModel):
    question: str
    descriptors: list[dict]


router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat/mcp-tool-plan")
async def mcp_tool_plan_api(
    body: McpToolPlanIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """FR-X2: Plan MCP tool calls for a question from registered system descriptors.

    Returns planned tool-call records with safe metadata only.
    Never returns auth secrets, bearer tokens, API keys, server URLs,
    or raw request/response payloads.
    """
    require_scope(sess, "bots")

    descs: list[MCPServerDescriptor] = []
    for d in body.descriptors:
        tools_raw = d.get("tools", [])
        tools = [
            MCPToolDescriptor(
                name=t.get("name", t.get("operation_id", "")),
                description=t.get("description", ""),
                operation_id=t.get("operation_id", ""),
                method=t.get("method", "GET"),
                path=t.get("path", ""),
                read_only=t.get("read_only", True),
                parameters=t.get("parameters", []),
            )
            for t in tools_raw
        ]
        descs.append(
            MCPServerDescriptor(
                system_id=d.get("system_id", ""),
                mcp_server_name=d.get("mcp_server_name", ""),
                tools=tools,
                spec_summary=d.get("spec_summary", {}),
            )
        )

    return build_mcp_tool_plan_response(descriptors=descs, question=body.question)

