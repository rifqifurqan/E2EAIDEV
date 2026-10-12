#!/usr/bin/env python3
"""Generate FR-F22 API reference docs from the live FastAPI OpenAPI schema.

Outputs:
- docs/openapi.json
- docs/en/api-reference.md
- docs/id/referensi-api.md

The generated Markdown intentionally includes only route metadata from the OpenAPI
schema: method, path, summary, operation id, tags, and response status codes. It
never includes local environment values, tokens, passwords, or request examples.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
API_SRC = REPO / "apps" / "api" / "src"
DOCS = REPO / "docs"

if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from e2eai.main import create_app  # noqa: E402

METHOD_ORDER = ["get", "post", "put", "patch", "delete", "options", "head"]


def _sorted_operations(schema: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    operations: list[tuple[str, str, dict[str, Any]]] = []
    for path in sorted(schema.get("paths", {})):
        path_item = schema["paths"][path]
        for method in METHOD_ORDER:
            if method in path_item:
                operations.append((path, method.upper(), path_item[method]))
    return operations


def _status_codes(operation: dict[str, Any]) -> str:
    codes = sorted(str(code) for code in operation.get("responses", {}))
    return ", ".join(codes) if codes else "not declared"


def _tag(operation: dict[str, Any]) -> str:
    tags = operation.get("tags") or ["untagged"]
    return str(tags[0])


def _safe_summary(operation: dict[str, Any]) -> str:
    summary = operation.get("summary") or operation.get("operationId") or "No summary"
    return str(summary).replace("\n", " ").strip()


def _render_en(schema: dict[str, Any]) -> str:
    operations = _sorted_operations(schema)
    lines = [
        "# E2EAIDEV API Reference",
        "",
        "<!-- GENERATED FROM apps/api FastAPI OpenAPI. Do not edit by hand; run scripts/generate_api_reference.py. -->",
        "",
        "Requirement: FR-F22 (P1 API reference).",
        "",
        f"API title: {schema['info']['title']}",
        f"API version: {schema['info']['version']}",
        f"Total paths: {len(schema.get('paths', {}))}",
        f"Total operations: {len(operations)}",
        "",
        "## How to regenerate",
        "",
        "    uv --project apps/api run python scripts/generate_api_reference.py",
        "",
        "## Authentication",
        "",
        "Most application routes require a scoped session or API key. This generated reference documents route shape only and never includes live credential values.",
        "",
        "## Operations by tag",
        "",
    ]
    grouped: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
    for path, method, op in operations:
        grouped.setdefault(_tag(op), []).append((path, method, op))

    for tag in sorted(grouped):
        lines.append(f"### {tag}")
        lines.append("")
        for path, method, op in grouped[tag]:
            lines.append(f"#### {method} {path}")
            lines.append("")
            lines.append(f"- Summary: {_safe_summary(op)}")
            lines.append(f"- Operation ID: `{op.get('operationId', 'not declared')}`")
            lines.append(f"- Response status codes: {_status_codes(op)}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_id(schema: dict[str, Any]) -> str:
    operations = _sorted_operations(schema)
    lines = [
        "# Referensi API E2EAIDEV",
        "",
        "<!-- DIHASILKAN DARI FastAPI OpenAPI apps/api. Jangan edit manual; jalankan scripts/generate_api_reference.py. -->",
        "",
        "Requirement: FR-F22 (referensi API P1).",
        "",
        f"Judul API: {schema['info']['title']}",
        f"Versi API: {schema['info']['version']}",
        f"Total path: {len(schema.get('paths', {}))}",
        f"Total operasi: {len(operations)}",
        "",
        "## Cara generate ulang",
        "",
        "    uv --project apps/api run python scripts/generate_api_reference.py",
        "",
        "## Autentikasi",
        "",
        "Sebagian besar route aplikasi memerlukan sesi atau API key berscope. Referensi generated ini hanya mendokumentasikan bentuk route dan tidak pernah memuat nilai kredensial live.",
        "",
        "## Operasi berdasarkan tag",
        "",
    ]
    grouped: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
    for path, method, op in operations:
        grouped.setdefault(_tag(op), []).append((path, method, op))

    for tag in sorted(grouped):
        lines.append(f"### {tag}")
        lines.append("")
        for path, method, op in grouped[tag]:
            lines.append(f"#### {method} {path}")
            lines.append("")
            lines.append(f"- Ringkasan: {_safe_summary(op)}")
            lines.append(f"- Operation ID: `{op.get('operationId', 'not declared')}`")
            lines.append(f"- Kode status respons: {_status_codes(op)}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def generate() -> None:
    app = create_app()
    schema = app.openapi()

    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "en").mkdir(parents=True, exist_ok=True)
    (DOCS / "id").mkdir(parents=True, exist_ok=True)

    (DOCS / "openapi.json").write_text(
        json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (DOCS / "en" / "api-reference.md").write_text(_render_en(schema), encoding="utf-8")
    (DOCS / "id" / "referensi-api.md").write_text(_render_id(schema), encoding="utf-8")

    print(
        "Generated docs/openapi.json, docs/en/api-reference.md, "
        "and docs/id/referensi-api.md "
        f"from {len(schema.get('paths', {}))} OpenAPI paths."
    )


if __name__ == "__main__":
    generate()
