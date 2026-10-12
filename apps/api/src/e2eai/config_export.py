"""FR-F21: secret-safe configuration-as-code export for the admin UI."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .auth import current_session, require_scope
from .core.config import repo_root
from .core.errors import AppError
from .db import get_session

SECRET_KEY_MARKERS = ("password", "secret", "token", "credential", "api_key", "apikey", "key")
SECRET_VALUE_MARKERS = ("gho_", "sk-", "bearer ", "password=", "api key value")
SUPPORTED_FORMATS = {"yaml", "json"}

router = APIRouter(prefix="/api/v1/admin/config", tags=["admin-config"])


def normalize_export_format(value: str) -> str:
    """Return a supported export format or fail closed for env/secrets-like formats."""
    fmt = (value or "yaml").lower().strip()
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported config export format: {value}")
    return fmt


def _looks_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in SECRET_KEY_MARKERS)


def _redacted_env_ref(key: str) -> str:
    safe = "".join(ch if ch.isalnum() else "_" for ch in key.upper()).strip("_") or "SECRET"
    return f"env:REDACTED_{safe}"


def _sanitize_value(value: Any, *, key: str = "") -> Any:
    if isinstance(value, dict):
        return {k: _sanitize_value(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(item, key=key) for item in value]
    if isinstance(value, str):
        lowered = value.lower()
        if _looks_secret_key(key):
            return value if value.startswith("env:") else _redacted_env_ref(key)
        if any(marker in lowered for marker in SECRET_VALUE_MARKERS):
            return "[REDACTED]"
    return value


def build_config_export(source_config: dict[str, Any], *, actor: str) -> dict[str, Any]:
    """Build a deterministic, secret-safe config export from the current install config.

    The export preserves configuration-as-code shape while replacing any inline secret-looking
    values with env references. It is safe for git diffing and UI download.
    """
    cfg = _sanitize_value(deepcopy(source_config))
    cfg.setdefault("limits", {"upload_mb": 100, "files_per_batch": 50, "storage_gb_per_user": 20})
    cfg.setdefault("retention", {"chats_days": 365, "traces_days": 30, "trash_days": 30, "audit_days": 365})
    cfg["export_metadata"] = {
        "schema_version": "e2eai.config.v1",
        "source": "admin_ui",
        "exported_by": actor,
        "secret_policy": "secrets are env: references only; inline secret-like values are redacted",
    }
    return cfg


def render_config_export_yaml(exported: dict[str, Any]) -> str:
    """Render exported config as stable YAML with a no-secrets header."""
    header = "# Exported from E2EAIDEV Admin UI (FR-F21). Secrets are env references only.\n"
    return header + yaml.safe_dump(exported, sort_keys=False, allow_unicode=True)


def load_current_config(root: Path | None = None) -> dict[str, Any]:
    """Load the current e2eai.yaml config file."""
    base = root or repo_root()
    config_path = base / "e2eai.yaml"
    if not config_path.exists():
        raise AppError(404, "Config not found", "Run the install wizard before exporting configuration.")
    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise AppError(500, "Invalid config", "e2eai.yaml must contain a mapping.")
    return loaded


@router.get("/export")
async def export_config_api(
    format: str = Query("yaml", pattern="^(yaml|json)$"),
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> Response:
    """Export the current install as configuration-as-code from the Admin UI (FR-F21)."""
    require_scope(sess, "admin")
    try:
        fmt = normalize_export_format(format)
    except ValueError as exc:
        raise AppError(400, "Unsupported export format", str(exc)) from exc

    actor = f"user:{sess.get('user_id', 'unknown')}"
    exported = build_config_export(load_current_config(), actor=actor)
    await audit.record(db, actor, "admin.config.export", "config:e2eai.yaml", {"format": fmt})
    await db.commit()

    if fmt == "json":
        return JSONResponse(exported, headers={"Content-Disposition": "attachment; filename=e2eai.json"})
    return PlainTextResponse(
        render_config_export_yaml(exported),
        media_type="application/yaml",
        headers={"Content-Disposition": "attachment; filename=e2eai.yaml"},
    )
