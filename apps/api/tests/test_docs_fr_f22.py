"""FR-F22 P1 docs: generated API reference and Lab adapter developer guide."""

from __future__ import annotations

import json
from pathlib import Path

from e2eai.main import create_app

ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT / "docs"


def test_api_reference_docs_are_generated_from_fastapi_openapi() -> None:
    """API reference docs must be generated from the live FastAPI OpenAPI schema."""
    en = DOCS / "en" / "api-reference.md"
    id_ = DOCS / "id" / "referensi-api.md"

    assert en.is_file(), "English generated API reference is missing"
    assert id_.is_file(), "Indonesian generated API reference is missing"

    schema = create_app().openapi()
    content = en.read_text(encoding="utf-8")

    assert "<!-- GENERATED FROM apps/api FastAPI OpenAPI" in content
    assert schema["info"]["title"] in content
    assert schema["info"]["version"] in content
    for path in ["/api/v1/health", "/api/v1/chat/conversations", "/api/v1/evals/datasets"]:
        assert path in schema["paths"]
        assert path in content

    # The reference may document auth schemes, but it must not contain live credentials or examples.
    # Use patterns that match actual credential formats, not substrings that appear in route paths
    # (e.g. "sk-" appears in "risk-classification").
    import re as _re
    lowered = content.lower()
    secret_patterns = [
        r"gho_[a-z0-9]+",            # GitHub token prefix
        r"sk-[a-z0-9_-]{16,}",        # OpenAI-style key (sk- followed by 16+ chars)
        r"bearer token",
        r"api key value",
        r"password=",
    ]
    assert not any(_re.search(p, lowered) for p in secret_patterns), \
        f"Unsafe credential marker found in api-reference.md"

    id_content = id_.read_text(encoding="utf-8")
    assert "Referensi API" in id_content
    assert "/api/v1/health" in id_content


def test_openapi_json_artifact_matches_live_schema() -> None:
    """Generated OpenAPI JSON artifact must match app.openapi() exactly for path coverage."""
    artifact = DOCS / "openapi.json"
    assert artifact.is_file(), "docs/openapi.json is missing"

    generated = json.loads(artifact.read_text(encoding="utf-8"))
    live = create_app().openapi()

    assert generated["info"] == live["info"]
    assert set(generated["paths"]) == set(live["paths"])
    assert "/api/v1/systems/{system_id}/mcp-descriptor" in generated["paths"]


def test_lab_adapter_developer_guides_cover_contract_and_isolation() -> None:
    """Lab adapter guide must explain the FR-F8 contract in EN and ID."""
    en = DOCS / "en" / "lab-adapter-developer-guide.md"
    id_ = DOCS / "id" / "panduan-developer-adapter-lab.md"

    assert en.is_file(), "English Lab adapter developer guide is missing"
    assert id_.is_file(), "Indonesian Lab adapter developer guide is missing"

    content = en.read_text(encoding="utf-8")
    required = [
        "Adapter Contract",
        "GET /info",
        "GET /health",
        "POST /run",
        "ToolAdapter",
        "check_adapter_contract",
        "own container",
        "No Secrets",
        "Contract Tests",
    ]
    for marker in required:
        assert marker in content

    id_content = id_.read_text(encoding="utf-8")
    assert "Kontrak Adapter" in id_content
    assert "GET /info" in id_content
    assert "POST /run" in id_content
