"""FR-F6 air-gapped install bundle planning.

The first deterministic/offline slice builds a secret-free manifest and operator
runbook for collecting pinned image tarballs, a model mirror, and offline docs.
It does not pull images or download models during tests.
"""

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from e2eai_wizard.airgap import build_airgap_manifest, render_airgap_runbook, validate_pinned_images
from e2eai_wizard.cli import app


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "deploy" / "compose").mkdir(parents=True)
    (tmp_path / "deploy" / "versions.lock").write_text(
        "images:\n"
        "  postgres: pgvector/pgvector:0.8.7@sha256:abc\n"
        "  valkey: valkey/valkey:9.1.2@sha256:def\n",
        encoding="utf-8",
    )
    (tmp_path / "catalog").mkdir()
    real_catalog = Path(__file__).resolve().parents[2] / "catalog" / "models.yaml"
    (tmp_path / "catalog" / "models.yaml").write_text(real_catalog.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "docs" / "en").mkdir(parents=True)
    (tmp_path / "docs" / "en" / "admin-operator-guide.md").write_text("# Admin\n", encoding="utf-8")
    (tmp_path / "e2eai.yaml").write_text(
        yaml.safe_dump(
            {
                "models": {
                    "chat": ["qwen3:1.7b"],
                    "embedding": ["bge-m3"],
                    "reranker": [],
                    "vision": [],
                    "safety": [],
                    "external": [{"provider": "openai", "model": "gpt-5-mini"}],
                }
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_airgap_manifest_includes_pinned_images_models_and_docs_without_secrets(tmp_path):
    root = _repo(tmp_path)

    manifest = build_airgap_manifest(root, bundle_dir="dist/e2eai-airgap")

    assert manifest["requirement"] == "FR-F6"
    assert manifest["bundle_dir"] == "dist/e2eai-airgap"
    assert manifest["images"] == [
        {"name": "postgres", "ref": "pgvector/pgvector:0.8.7@sha256:abc", "tar": "images/postgres.tar"},
        {"name": "valkey", "ref": "valkey/valkey:9.1.2@sha256:def", "tar": "images/valkey.tar"},
    ]
    assert {m["id"] for m in manifest["models"]} == {"qwen3:1.7b", "bge-m3"}
    assert all(m["mirror_path"].startswith("models/") for m in manifest["models"])
    assert manifest["external_models"] == [{"provider": "openai", "model": "gpt-5-mini"}]
    assert manifest["docs"] == ["docs/en/admin-operator-guide.md"]
    assert "password" not in str(manifest).lower()
    assert "token" not in str(manifest).lower()


def test_airgap_rejects_floating_images_and_renders_operator_runbook(tmp_path):
    root = _repo(tmp_path)
    bad = {"postgres": "postgres:17"}
    with pytest.raises(ValueError, match="pinned by digest"):
        validate_pinned_images(bad)

    runbook = render_airgap_runbook(build_airgap_manifest(root, bundle_dir="dist/e2eai-airgap"))
    assert "# E2EAIDEV air-gapped bundle plan" in runbook
    assert "docker pull pgvector/pgvector:0.8.7@sha256:abc" in runbook
    assert "docker save -o dist/e2eai-airgap/images/postgres.tar" in runbook
    assert "ollama pull qwen3:1.7b" in runbook
    assert "docs/en/admin-operator-guide.md" in runbook
    assert "env:" not in runbook.lower()
    assert "password" not in runbook.lower()
    assert "token" not in runbook.lower()


def test_airgap_plan_cli_outputs_secret_free_plan(tmp_path):
    root = _repo(tmp_path)
    result = CliRunner().invoke(app, ["airgap-plan", "--root", str(root), "--bundle-dir", "dist/e2eai-airgap"])

    assert result.exit_code == 0, result.output
    assert "E2EAIDEV air-gapped bundle plan" in result.output
    assert "pgvector/pgvector:0.8.7@sha256:abc" in result.output
    assert "qwen3:1.7b" in result.output
    assert "password" not in result.output.lower()
