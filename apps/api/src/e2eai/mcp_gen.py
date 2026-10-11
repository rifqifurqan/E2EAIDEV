"""OpenAPI-to-MCP server descriptor generator for admin-registered systems (FR-B4).

Converts a validated OpenAPI 3.x spec into a safe MCP server descriptor:
a tool list with allowed operations, read_only flags, and safe parameter
metadata. Auth secrets, security scheme details, and server URLs are never
included in the output.

One MCP server descriptor is generated per registered external system.
Delegated identity / token-exchange (FR-X3) and write-action confirmation
(FR-X5) are future slices; this module only produces the static descriptor.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import current_session, require_scope
from .core.errors import AppError
from .db import get_session

MAX_OPERATIONS = 200  # safety: reject specs with more operations than this

_READ_ONLY_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# HTTP methods defined in the OpenAPI path item object
_HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")


@dataclass
class MCPToolDescriptor:
    """Safe descriptor for one MCP tool corresponding to one OpenAPI operation."""

    name: str
    description: str
    operation_id: str
    method: str  # uppercase, e.g. "GET"
    path: str
    read_only: bool
    parameters: list[dict] = field(default_factory=list)


@dataclass
class MCPServerDescriptor:
    """Safe MCP server descriptor for one admin-registered external system."""

    system_id: str
    mcp_server_name: str
    tools: list[MCPToolDescriptor]
    spec_summary: dict


# ---------------------------------------------------------------------------
# Spec validation
# ---------------------------------------------------------------------------


def validate_openapi_spec(spec: dict) -> list[str]:
    """Validate a minimal OpenAPI 3.x spec.

    Returns a list of validation error strings. An empty list means the spec
    is acceptable for descriptor generation.

    Checks:
    - ``openapi`` field present
    - Version is 3.x (2.x / Swagger not supported)
    - ``info`` field present
    - ``paths`` field present and non-empty
    - Total operation count within MAX_OPERATIONS safety limit

    Does NOT make network calls, does NOT inspect auth credentials.
    """
    errors: list[str] = []

    if "openapi" not in spec:
        errors.append("Missing required 'openapi' field")
        # Cannot proceed with further checks
        return errors

    version = str(spec["openapi"])
    if not version.startswith("3."):
        errors.append(
            f"OpenAPI version must be 3.x (found '{version}'); "
            "Swagger 2.0 and earlier are not supported"
        )

    if "info" not in spec:
        errors.append("Missing required 'info' field")

    if "paths" not in spec:
        errors.append("Missing required 'paths' field")
    elif not spec["paths"]:
        errors.append("'paths' is empty; at least one path with operations is required")
    else:
        total_ops = _count_operations(spec["paths"])
        if total_ops > MAX_OPERATIONS:
            errors.append(
                f"Spec has too many operations ({total_ops}); "
                f"limit is {MAX_OPERATIONS} per registered system"
            )

    return errors


def _count_operations(paths: dict) -> int:
    """Count total HTTP operations defined across all path items."""
    count = 0
    for path_item in paths.values():
        if not isinstance(path_item, dict):
            continue
        for method in _HTTP_METHODS:
            if method in path_item:
                count += 1
    return count


def _extract_operations(paths: dict) -> list[dict]:
    """Extract all operations from path items as a flat list.

    Operations without an ``operationId`` are skipped (cannot be referenced
    by name in allowed_operation_ids).

    Returns dicts with keys: operation_id, method (uppercase), path, summary,
    parameters (list, may be empty).
    """
    ops: list[dict] = []
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method in _HTTP_METHODS:
            if method not in path_item:
                continue
            op = path_item[method]
            if not isinstance(op, dict):
                continue
            operation_id = op.get("operationId") or op.get("operation_id")
            if not operation_id:
                continue  # skip anonymous operations
            ops.append(
                {
                    "operation_id": str(operation_id),
                    "method": method.upper(),
                    "path": path,
                    "summary": op.get("summary", ""),
                    "parameters": op.get("parameters") or [],
                }
            )
    return ops


def _sanitize_schema(schema: object) -> dict:
    """Return dependency-free structural schema metadata safe for descriptors.

    OpenAPI schemas often carry examples/defaults/descriptions that can include
    sample credentials or internal values. MCP descriptors only need shape data,
    so keep a conservative JSON-Schema subset and recurse into nested shapes.
    """
    if not isinstance(schema, dict):
        return {}

    safe: dict = {}
    for key in ("type", "format", "enum"):
        if key in schema:
            safe[key] = schema[key]

    if isinstance(schema.get("items"), dict):
        safe["items"] = _sanitize_schema(schema["items"])

    properties = schema.get("properties")
    if isinstance(properties, dict):
        safe_properties = {
            str(name): _sanitize_schema(value)
            for name, value in properties.items()
            if isinstance(value, dict)
        }
        if safe_properties:
            safe["properties"] = safe_properties

    if isinstance(schema.get("required"), list):
        safe["required"] = [str(item) for item in schema["required"]]

    return safe


def _sanitize_parameter(parameter: dict) -> dict:
    """Keep only safe OpenAPI parameter metadata for MCP tool descriptors."""
    safe = {k: parameter[k] for k in ("name", "in", "required") if k in parameter}
    schema = _sanitize_schema(parameter.get("schema"))
    if schema:
        safe["schema"] = schema
    return safe


# ---------------------------------------------------------------------------
# Descriptor builder
# ---------------------------------------------------------------------------


def build_mcp_server_descriptor(
    system_id: str,
    spec: dict,
    allowed_operation_ids: list[str] | None = None,
    operation_overrides: dict[str, dict] | None = None,
) -> MCPServerDescriptor:
    """Build a safe MCP server descriptor from a validated OpenAPI 3.x spec.

    Args:
        system_id: Admin-assigned identifier for the external system.
        spec: OpenAPI 3.x spec dict (caller is responsible for loading).
        allowed_operation_ids: If provided, only operations whose
            ``operationId`` appears in this list are included as tools.
            Unknown IDs are silently skipped.  ``None`` means all operations
            with an ``operationId`` are included.
        operation_overrides: Per-operation metadata.  Keys are operationIds;
            the only currently honoured key is ``"read_only"`` (bool), which
            overrides the HTTP-method-based default.

    Returns:
        MCPServerDescriptor — safe, serialisable, contains no secrets.

    Raises:
        ValueError: If ``validate_openapi_spec`` finds errors.  The exception
            message is a semicolon-joined list of all errors.

    Security contract:
        - ``components.securitySchemes`` and ``security`` blocks are ignored
          and never included in the output.
        - ``servers`` URLs are not included in the output.
        - Raw request bodies, response schemas, and example values are not
          stored in the descriptor (parameters list carries only safe metadata:
          name, in, required, schema).
    """
    errors = validate_openapi_spec(spec)
    if errors:
        raise ValueError("; ".join(errors))

    all_ops = _extract_operations(spec.get("paths", {}))
    total_operation_count = len(all_ops)

    allowed_set: set[str] | None = set(allowed_operation_ids) if allowed_operation_ids else None
    overrides = operation_overrides or {}

    tools: list[MCPToolDescriptor] = []
    for op in all_ops:
        op_id = op["operation_id"]

        # Honour the allowed-operations filter
        if allowed_set is not None and op_id not in allowed_set:
            continue

        # Determine read_only: method-based default, then explicit override
        override = overrides.get(op_id, {})
        if "read_only" in override:
            read_only = bool(override["read_only"])
        else:
            read_only = op["method"] in _READ_ONLY_METHODS

        # Keep only safe parameter metadata (no requestBody, no response, no
        # security, no extensions); _sanitize_parameter strips examples/defaults/descriptions
        safe_params = [
            _sanitize_parameter(p)
            for p in op["parameters"]
            if isinstance(p, dict)
        ]

        tools.append(
            MCPToolDescriptor(
                name=op_id,
                description=op["summary"] or op_id,
                operation_id=op_id,
                method=op["method"],
                path=op["path"],
                read_only=read_only,
                parameters=safe_params,
            )
        )

    info = spec.get("info", {})

    return MCPServerDescriptor(
        system_id=system_id,
        mcp_server_name=f"{system_id}.mcp",
        tools=tools,
        spec_summary={
            "spec_title": info.get("title", ""),
            "spec_version": info.get("version", ""),
            "total_operation_count": total_operation_count,
            "allowed_count": len(tools),
        },
    )


# ---------------------------------------------------------------------------
# FastAPI route (FR-B4)
# ---------------------------------------------------------------------------


class McpDescriptorIn(BaseModel):
    spec: dict
    allowed_operation_ids: list[str] | None = None
    operation_overrides: dict[str, dict] | None = None


router = APIRouter(prefix="/api/v1/systems", tags=["systems"])


@router.post("/{system_id}/mcp-descriptor")
async def mcp_descriptor_api(
    system_id: str,
    body: McpDescriptorIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """FR-B4: Generate a safe MCP server descriptor from an uploaded OpenAPI 3.x spec.

    Validates the spec, selects allowed operations, and returns a tool list
    with read_only flags and safe parameter metadata.

    Never returns auth secrets, bearer tokens, API keys, security scheme
    details, or server URLs from the spec.
    """
    require_scope(sess, "bots")

    errors = validate_openapi_spec(body.spec)
    if errors:
        raise AppError(422, f"OpenAPI spec validation failed: {'; '.join(errors)}")

    try:
        descriptor = build_mcp_server_descriptor(
            system_id=system_id,
            spec=body.spec,
            allowed_operation_ids=body.allowed_operation_ids,
            operation_overrides=body.operation_overrides,
        )
    except ValueError as exc:
        raise AppError(422, str(exc)) from exc

    return {
        "system_id": descriptor.system_id,
        "mcp_server_name": descriptor.mcp_server_name,
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "operation_id": t.operation_id,
                "method": t.method,
                "path": t.path,
                "read_only": t.read_only,
                "parameters": t.parameters,
            }
            for t in descriptor.tools
        ],
        "spec_summary": descriptor.spec_summary,
    }
