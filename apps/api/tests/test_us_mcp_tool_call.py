"""FR-X2 Live MCP tool-call planner: question-time tool selection and no-vectorize guard.

At question time the system plans MCP tool calls from existing descriptors.
Live tool results are NEVER indexed or vectorized. Tests verify:
- Tool-call planning from an MCP descriptor + question
- Safe output: no auth secrets, server URLs, raw payloads, or credentials
- Vectorize/embed guard rejects live tool results
- read_only enforcement: mutating tools require confirmation flag
- Audit records planned calls with safe metadata only
- API route wiring
"""

import pytest

from e2eai.mcp_gen import MCPServerDescriptor, MCPToolDescriptor, build_mcp_server_descriptor
from e2eai.mcp_tool_call import (
    LiveToolResult,
    MCPToolCallRecord,
    build_mcp_tool_plan_response,
    plan_mcp_tool_calls,
    reject_vectorize_live_result,
)

# ---------------------------------------------------------------------------
# Fixtures: reuse the HR API spec from mcp_gen tests
# ---------------------------------------------------------------------------

HR_DESCRIPTOR = MCPServerDescriptor(
    system_id="hr-system",
    mcp_server_name="hr-system.mcp",
    tools=[
        MCPToolDescriptor(
            name="list_employees",
            description="List all employees",
            operation_id="list_employees",
            method="GET",
            path="/employees",
            read_only=True,
            parameters=[{"name": "department", "in": "query", "required": False, "schema": {"type": "string"}}],
        ),
        MCPToolDescriptor(
            name="get_employee",
            description="Get employee by ID",
            operation_id="get_employee",
            method="GET",
            path="/employees/{id}",
            read_only=True,
            parameters=[{"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}],
        ),
        MCPToolDescriptor(
            name="create_employee",
            description="Create a new employee",
            operation_id="create_employee",
            method="POST",
            path="/employees",
            read_only=False,
            parameters=[],
        ),
    ],
    spec_summary={"spec_title": "HR API", "spec_version": "1.0.0", "total_operation_count": 3, "allowed_count": 3},
)


# ---------------------------------------------------------------------------
# Tool-call planning
# ---------------------------------------------------------------------------


def test_plan_selects_relevant_tools_from_descriptor():
    """A question about employees should match employee-related tools."""
    records = plan_mcp_tool_calls(
        descriptors=[HR_DESCRIPTOR],
        question="How many employees are in the Sales department?",
    )
    assert len(records) >= 1
    op_ids = {r.operation_id for r in records}
    assert "list_employees" in op_ids
    for r in records:
        assert isinstance(r, MCPToolCallRecord)


def test_plan_returns_empty_for_unrelated_question():
    """A question about weather should not match any HR tools."""
    records = plan_mcp_tool_calls(
        descriptors=[HR_DESCRIPTOR],
        question="What is the weather forecast for tomorrow?",
    )
    assert records == []


def test_plan_returns_empty_for_empty_descriptors():
    records = plan_mcp_tool_calls(descriptors=[], question="How many employees?")
    assert records == []


def test_plan_record_carries_safe_metadata():
    """Records must carry operation_id, method, path, read_only, system_id but no secrets."""
    records = plan_mcp_tool_calls(
        descriptors=[HR_DESCRIPTOR],
        question="List employees in the sales department",
    )
    assert len(records) >= 1
    r = records[0]
    assert r.system_id == "hr-system"
    assert r.operation_id == "list_employees"
    assert r.method == "GET"
    assert r.path == "/employees"
    assert r.read_only is True
    # Safe: no auth, no URL, no payload
    serialized = str(r)
    assert "bearer" not in serialized.lower()
    assert "api-key" not in serialized.lower().replace("_", "-")
    assert "secret" not in serialized.lower()


def test_plan_flags_mutating_tools_needing_confirmation():
    """Mutating (non-read_only) tools in the plan must be flagged as needs_confirmation=True."""
    records = plan_mcp_tool_calls(
        descriptors=[HR_DESCRIPTOR],
        question="Create a new employee named Alice in Engineering",
    )
    mutating = [r for r in records if not r.read_only]
    assert len(mutating) >= 1
    for r in mutating:
        assert r.needs_confirmation is True, (
            f"Mutating tool {r.operation_id} must have needs_confirmation=True"
        )


def test_plan_response_does_not_echo_raw_question_or_payload():
    """Question text may contain secrets; route/helper responses expose only safe call metadata."""
    response = build_mcp_tool_plan_response(
        descriptors=[HR_DESCRIPTOR],
        question="List employees with bearer token prod-secret-api-key",
    )
    serialized = str(response).lower()
    assert "question" not in response
    assert "prod-secret-api-key" not in serialized
    assert "bearer token" not in serialized
    assert response["total"] >= 1
    assert response["planned_calls"][0]["operation_id"] == "list_employees"


def test_plan_read_only_tools_do_not_need_confirmation():
    records = plan_mcp_tool_calls(
        descriptors=[HR_DESCRIPTOR],
        question="List all employees",
    )
    read_only = [r for r in records if r.read_only]
    assert len(read_only) >= 1
    for r in read_only:
        assert r.needs_confirmation is False


# ---------------------------------------------------------------------------
# No-vectorize guard (FR-X2 core invariant)
# ---------------------------------------------------------------------------


def test_reject_vectorize_live_result_raises():
    """Attempting to vectorize/embed/index a live tool result must raise."""
    result = LiveToolResult(
        system_id="hr-system",
        operation_id="list_employees",
        source="live_mcp",
    )
    with pytest.raises(ValueError, match="[Ll]ive.*tool.*result.*must not.*vector|index|embed"):
        reject_vectorize_live_result(result)


def test_reject_vectorize_marks_source_as_live():
    """LiveToolResult always declares its source as live_mcp."""
    result = LiveToolResult(
        system_id="hr-system",
        operation_id="get_employee",
        source="live_mcp",
    )
    assert result.source == "live_mcp"
    assert result.vectorizable is False


# ---------------------------------------------------------------------------
# Multiple descriptors
# ---------------------------------------------------------------------------


ERP_DESCRIPTOR = MCPServerDescriptor(
    system_id="erp-system",
    mcp_server_name="erp-system.mcp",
    tools=[
        MCPToolDescriptor(
            name="get_purchase_order",
            description="Get purchase order details",
            operation_id="get_purchase_order",
            method="GET",
            path="/purchase-orders/{id}",
            read_only=True,
            parameters=[{"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}],
        ),
    ],
    spec_summary={"spec_title": "ERP API", "spec_version": "2.0.0", "total_operation_count": 1, "allowed_count": 1},
)


def test_plan_matches_across_multiple_descriptors():
    """When multiple descriptors are provided, tools from the right system are selected."""
    records = plan_mcp_tool_calls(
        descriptors=[HR_DESCRIPTOR, ERP_DESCRIPTOR],
        question="Show me the purchase order details",
    )
    op_ids = {r.operation_id for r in records}
    assert "get_purchase_order" in op_ids
    # Should NOT include unrelated HR tools
    assert "list_employees" not in op_ids


# ---------------------------------------------------------------------------
# API route wiring
# ---------------------------------------------------------------------------


def test_mcp_tool_call_plan_route_is_wired():
    """POST /api/v1/chat/mcp-tool-plan is registered in the FastAPI app."""
    from e2eai.main import app

    openapi = app.openapi()
    assert "/api/v1/chat/mcp-tool-plan" in openapi["paths"], (
        f"Route not found. Registered paths: {sorted(openapi['paths'].keys())}"
    )
