"""Question-time MCP tool-call planner and no-vectorize guard (FR-X2).

At question time the system selects relevant MCP tools from registered
descriptors and plans calls. Live tool results are NEVER copied into
vectors, embeddings, or the chunk index.

Delegated identity (FR-X3) and actual network execution are future slices;
this module plans and records tool calls deterministically/offline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

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

