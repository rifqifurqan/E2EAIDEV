"""FR-B4 MCP server descriptor generation from OpenAPI.

Each admin-registered external system gets one MCP server descriptor
generated from its uploaded OpenAPI spec. Tests verify:
- Spec validation (accepts valid, rejects bad/unsupported/unsafe)
- Tool-list generation from allowed operations
- read_only flag defaults (GET = True, mutating = False)
- Explicit read_only override in allowed-operation metadata
- Auth secrets never included in output
- Route wiring
"""

import pytest

from e2eai.mcp_gen import (
    MAX_OPERATIONS,
    MCPServerDescriptor,
    MCPToolDescriptor,
    build_mcp_server_descriptor,
    validate_openapi_spec,
)

# ---------------------------------------------------------------------------
# Minimal valid OpenAPI 3 spec fixture
# ---------------------------------------------------------------------------

MINIMAL_SPEC: dict = {
    "openapi": "3.0.3",
    "info": {"title": "HR API", "version": "1.0.0"},
    "paths": {
        "/employees": {
            "get": {
                "operationId": "list_employees",
                "summary": "List all employees",
                "parameters": [
                    {
                        "name": "department",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string"},
                    }
                ],
            },
            "post": {
                "operationId": "create_employee",
                "summary": "Create a new employee",
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {"type": "object"}}},
                },
            },
        },
        "/employees/{id}": {
            "get": {
                "operationId": "get_employee",
                "summary": "Get employee by ID",
                "parameters": [
                    {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}
                ],
            },
            "patch": {
                "operationId": "update_employee",
                "summary": "Update employee fields",
            },
            "delete": {
                "operationId": "delete_employee",
                "summary": "Delete an employee",
            },
        },
    },
    "components": {
        "securitySchemes": {
            "BearerAuth": {"type": "http", "scheme": "bearer"},
        }
    },
}


# ---------------------------------------------------------------------------
# Spec validation
# ---------------------------------------------------------------------------


def test_validate_accepts_minimal_valid_spec():
    errors = validate_openapi_spec(MINIMAL_SPEC)
    assert errors == [], f"Expected no errors, got: {errors}"


def test_validate_rejects_missing_openapi_field():
    bad = {k: v for k, v in MINIMAL_SPEC.items() if k != "openapi"}
    errors = validate_openapi_spec(bad)
    assert any("openapi" in e.lower() for e in errors), f"Expected openapi error, got: {errors}"


def test_validate_rejects_openapi_2x_spec():
    bad = {**MINIMAL_SPEC, "openapi": "2.0"}
    errors = validate_openapi_spec(bad)
    assert any("version" in e.lower() or "3." in e for e in errors), f"Got: {errors}"


def test_validate_rejects_missing_paths():
    bad = {k: v for k, v in MINIMAL_SPEC.items() if k != "paths"}
    errors = validate_openapi_spec(bad)
    assert any("paths" in e.lower() for e in errors), f"Expected paths error, got: {errors}"


def test_validate_rejects_empty_paths():
    bad = {**MINIMAL_SPEC, "paths": {}}
    errors = validate_openapi_spec(bad)
    assert any("paths" in e.lower() or "empty" in e.lower() for e in errors), f"Got: {errors}"


def test_validate_rejects_spec_exceeding_max_operations():
    """Safety limit: reject specs with too many operations."""
    many_paths = {
        f"/resource/{i}": {"get": {"operationId": f"get_{i}", "summary": f"Get {i}"}}
        for i in range(MAX_OPERATIONS + 1)
    }
    bad = {**MINIMAL_SPEC, "paths": many_paths}
    errors = validate_openapi_spec(bad)
    assert any("too many" in e.lower() or "limit" in e.lower() for e in errors), f"Got: {errors}"


def test_validate_rejects_missing_info():
    bad = {k: v for k, v in MINIMAL_SPEC.items() if k != "info"}
    errors = validate_openapi_spec(bad)
    assert any("info" in e.lower() for e in errors), f"Expected info error, got: {errors}"


# ---------------------------------------------------------------------------
# Tool-list generation
# ---------------------------------------------------------------------------


def test_build_descriptor_generates_tool_per_allowed_operation():
    """Each entry in allowed_operation_ids produces exactly one MCPToolDescriptor."""
    descriptor = build_mcp_server_descriptor(
        system_id="hr-system",
        spec=MINIMAL_SPEC,
        allowed_operation_ids=["list_employees", "get_employee"],
    )
    assert isinstance(descriptor, MCPServerDescriptor)
    op_ids = {t.operation_id for t in descriptor.tools}
    assert op_ids == {"list_employees", "get_employee"}
    assert len(descriptor.tools) == 2


def test_build_descriptor_all_operations_when_no_filter():
    """If allowed_operation_ids is None/empty, all operations are included."""
    descriptor = build_mcp_server_descriptor(
        system_id="hr-system",
        spec=MINIMAL_SPEC,
        allowed_operation_ids=None,
    )
    op_ids = {t.operation_id for t in descriptor.tools}
    assert op_ids == {"list_employees", "create_employee", "get_employee", "update_employee", "delete_employee"}


def test_build_descriptor_get_operations_are_read_only_by_default():
    descriptor = build_mcp_server_descriptor(
        system_id="hr-system",
        spec=MINIMAL_SPEC,
        allowed_operation_ids=["list_employees", "get_employee"],
    )
    for tool in descriptor.tools:
        assert tool.read_only is True, f"{tool.operation_id} should be read_only=True (GET)"


def test_build_descriptor_mutating_operations_not_read_only_by_default():
    descriptor = build_mcp_server_descriptor(
        system_id="hr-system",
        spec=MINIMAL_SPEC,
        allowed_operation_ids=["create_employee", "update_employee", "delete_employee"],
    )
    for tool in descriptor.tools:
        assert tool.read_only is False, f"{tool.operation_id} should be read_only=False ({tool.method})"


def test_build_descriptor_explicit_read_only_override_on_post():
    """Metadata can explicitly mark a POST as read_only (e.g. search-by-POST pattern)."""
    descriptor = build_mcp_server_descriptor(
        system_id="hr-system",
        spec=MINIMAL_SPEC,
        allowed_operation_ids=["create_employee"],
        operation_overrides={"create_employee": {"read_only": True}},
    )
    tools_by_id = {t.operation_id: t for t in descriptor.tools}
    assert tools_by_id["create_employee"].read_only is True


def test_build_descriptor_tool_carries_method_and_path():
    descriptor = build_mcp_server_descriptor(
        system_id="hr-system",
        spec=MINIMAL_SPEC,
        allowed_operation_ids=["list_employees"],
    )
    tool = descriptor.tools[0]
    assert isinstance(tool, MCPToolDescriptor)
    assert tool.method == "GET"
    assert tool.path == "/employees"
    assert tool.name == "list_employees"


def test_build_descriptor_tool_carries_safe_description():
    descriptor = build_mcp_server_descriptor(
        system_id="hr-system",
        spec=MINIMAL_SPEC,
        allowed_operation_ids=["list_employees"],
    )
    assert descriptor.tools[0].description == "List all employees"


def test_build_descriptor_spec_summary_counts_are_correct():
    descriptor = build_mcp_server_descriptor(
        system_id="hr-system",
        spec=MINIMAL_SPEC,
        allowed_operation_ids=["list_employees", "get_employee"],
    )
    assert descriptor.spec_summary["allowed_count"] == 2
    assert descriptor.spec_summary["total_operation_count"] == 5  # 5 operations in MINIMAL_SPEC


def test_build_descriptor_ignores_unknown_allowed_operation_ids():
    """Unknown operationIds are silently skipped (not an error)."""
    descriptor = build_mcp_server_descriptor(
        system_id="hr-system",
        spec=MINIMAL_SPEC,
        allowed_operation_ids=["list_employees", "nonexistent_op"],
    )
    op_ids = {t.operation_id for t in descriptor.tools}
    assert op_ids == {"list_employees"}


# ---------------------------------------------------------------------------
# Security / no-leak guarantees
# ---------------------------------------------------------------------------


def test_build_descriptor_never_includes_auth_secrets_in_output():
    """securitySchemes, bearer tokens, api keys, and credentials must never appear in the descriptor."""
    descriptor = build_mcp_server_descriptor(
        system_id="hr-system",
        spec={
            **MINIMAL_SPEC,
            "components": {
                "securitySchemes": {
                    "BearerAuth": {"type": "http", "scheme": "bearer"},
                    "ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
                }
            },
        },
        allowed_operation_ids=None,
    )
    serialized = str(descriptor)
    assert "BearerAuth" not in serialized
    assert "ApiKeyAuth" not in serialized
    assert "bearer" not in serialized.lower()
    assert "api-key" not in serialized.lower().replace("_", "-")
    assert "x-api-key" not in serialized.lower()


def test_build_descriptor_output_never_contains_server_urls():
    """Server base URLs might leak internal network topology; exclude them."""
    spec_with_servers = {
        **MINIMAL_SPEC,
        "servers": [
            {"url": "https://internal.corp.example.com/api/v1"},
            {"url": "https://secret-service:8443"},
        ],
    }
    descriptor = build_mcp_server_descriptor(
        system_id="hr-system",
        spec=spec_with_servers,
        allowed_operation_ids=["list_employees"],
    )
    serialized = str(descriptor)
    assert "internal.corp.example.com" not in serialized
    assert "secret-service" not in serialized


def test_build_descriptor_parameter_schema_strips_examples_defaults_and_descriptions():
    """Parameter schemas may contain credentials/examples; only structural metadata is safe."""
    spec_with_parameter_secrets = {
        **MINIMAL_SPEC,
        "paths": {
            "/employees": {
                "get": {
                    "operationId": "list_employees",
                    "summary": "List all employees",
                    "parameters": [
                        {
                            "name": "department",
                            "in": "query",
                            "required": False,
                            "schema": {
                                "type": "string",
                                "format": "uuid",
                                "default": "prod-bearer-token-secret",
                                "example": "sk-live-secret",
                                "description": "internal credential format",
                            },
                        }
                    ],
                }
            }
        },
    }
    descriptor = build_mcp_server_descriptor(
        system_id="hr-system",
        spec=spec_with_parameter_secrets,
        allowed_operation_ids=["list_employees"],
    )
    serialized = str(descriptor)
    assert "prod-bearer-token-secret" not in serialized
    assert "sk-live-secret" not in serialized
    assert "internal credential format" not in serialized
    assert descriptor.tools[0].parameters == [
        {"name": "department", "in": "query", "required": False, "schema": {"type": "string", "format": "uuid"}}
    ]


def test_build_descriptor_raises_on_invalid_spec():
    """build_mcp_server_descriptor must raise ValueError when spec fails validation."""
    bad_spec = {"openapi": "2.0", "info": {"title": "x", "version": "1"}, "paths": {"/x": {}}}
    with pytest.raises(ValueError, match="openapi|version|paths"):
        build_mcp_server_descriptor(
            system_id="hr-system",
            spec=bad_spec,
            allowed_operation_ids=None,
        )


# ---------------------------------------------------------------------------
# Dataclass sanity
# ---------------------------------------------------------------------------


def test_mcp_tool_descriptor_fields_are_present():
    tool = MCPToolDescriptor(
        name="list_employees",
        description="List employees",
        operation_id="list_employees",
        method="GET",
        path="/employees",
        read_only=True,
        parameters=[{"name": "department", "in": "query", "required": False, "schema": {"type": "string"}}],
    )
    assert tool.name == "list_employees"
    assert tool.read_only is True
    assert tool.parameters[0]["name"] == "department"


# ---------------------------------------------------------------------------
# API route wiring smoke
# ---------------------------------------------------------------------------


def test_mcp_descriptor_api_route_is_wired():
    """POST /api/v1/systems/{system_id}/mcp-descriptor is registered in the FastAPI app."""
    from e2eai.main import app

    openapi = app.openapi()
    assert "/api/v1/systems/{system_id}/mcp-descriptor" in openapi["paths"], (
        f"Route not found. Registered paths: {sorted(openapi['paths'].keys())}"
    )
