"""FR-F21 P1: configuration-as-code export from the admin UI/API."""

from __future__ import annotations

import yaml


def test_config_export_preserves_install_shape_and_secret_refs_only() -> None:
    """Exported config can be versioned safely: install shape in, raw secrets out."""
    from e2eai.config_export import build_config_export, render_config_export_yaml

    source = {
        "tier": "lite",
        "components": {"auth": "oidc", "job_engine": "celery", "vector_store": "pgvector"},
        "services": {"postgres": {"port": 15432}, "litellm": {"port": 14000}},
        "models": {"chat": ["qwen3:4b"], "embedding": ["bge-m3"], "external": []},
        "egress": {"external_apis": False},
        "locale": {"default_language": "id", "time_zone": "Asia/Jakarta"},
        "secrets": {"db_password": "env:POSTGRES_PASSWORD", "oidc_client_secret": "raw-secret-that-must-not-export"},
    }

    exported = build_config_export(source, actor="user:admin")
    exported_yaml = render_config_export_yaml(exported)
    parsed = yaml.safe_load(exported_yaml)

    assert parsed["tier"] == "lite"
    assert parsed["components"]["auth"] == "oidc"
    assert parsed["models"]["chat"] == ["qwen3:4b"]
    assert parsed["secrets"]["db_password"] == "env:POSTGRES_PASSWORD"
    assert parsed["secrets"]["oidc_client_secret"] == "env:REDACTED_OIDC_CLIENT_SECRET"
    assert parsed["export_metadata"]["schema_version"] == "e2eai.config.v1"
    assert parsed["export_metadata"]["source"] == "admin_ui"
    assert parsed["export_metadata"]["exported_by"] == "user:admin"

    forbidden = ["raw-secret-that-must-not-export", "password=", "bearer ", "gho_", "sk-"]
    lowered = exported_yaml.lower()
    assert not any(marker in lowered for marker in forbidden)


def test_config_export_api_route_is_wired() -> None:
    """Admin UI download endpoint must be visible in the OpenAPI schema."""
    from e2eai.main import create_app

    openapi = create_app().openapi()
    path = "/api/v1/admin/config/export"
    assert path in openapi["paths"]
    assert "get" in openapi["paths"][path]


def test_config_export_rejects_unknown_format() -> None:
    """The export boundary only supports safe JSON/YAML formats."""
    from e2eai.config_export import normalize_export_format

    assert normalize_export_format("yaml") == "yaml"
    assert normalize_export_format("json") == "json"
    try:
        normalize_export_format("env")
    except ValueError as exc:
        assert "Unsupported config export format" in str(exc)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("env format should be rejected because it could look like a secrets file")
