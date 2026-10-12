"""Air-gapped install bundle planning (FR-F6).

The helper builds a deterministic, secret-free manifest for operators to collect:
- digest-pinned container image tarballs
- selected local model artifacts/mirror paths
- offline documentation files
It intentionally renders commands instead of pulling/downloading during tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from . import models


def _safe_slug(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "-" for ch in value).strip("-")


def validate_pinned_images(images: dict[str, str]) -> None:
    """FR-F6/NFR-9: offline bundles must use digest-pinned images, never floating tags."""
    for name, ref in images.items():
        if "@sha256:" not in ref:
            raise ValueError(f"Image {name} must be pinned by digest before it can enter an air-gapped bundle")


def _load_selected_models(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    config_path = root / "e2eai.yaml"
    if not config_path.exists():
        return [], []
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    selected = cfg.get("models", {}) or {}
    catalog = models.load_catalog(root)
    local_models: list[dict[str, Any]] = []
    for role in models.ROLES:
        for model_id in selected.get(role, []) or []:
            model = catalog[model_id]
            local_models.append(
                {
                    "id": model.id,
                    "role": model.role,
                    "served_by": model.served_by,
                    "source": model.source,
                    "license": model.license,
                    "size_gb": model.size_gb,
                    "mirror_path": f"models/{model.served_by}/{_safe_slug(model.source)}",
                }
            )
    external_models = [
        {"provider": str(row.get("provider", "")), "model": str(row.get("model", ""))}
        for row in selected.get("external", []) or []
    ]
    return local_models, external_models


def _docs(root: Path) -> list[str]:
    docs_root = root / "docs"
    if not docs_root.exists():
        return []
    return sorted(str(path.relative_to(root)).replace("\\", "/") for path in docs_root.rglob("*") if path.is_file())


def build_airgap_manifest(root: Path, bundle_dir: str = "dist/e2eai-airgap") -> dict[str, Any]:
    """Build the secret-free FR-F6 air-gap manifest from repo pins/config/docs."""
    versions = yaml.safe_load((root / "deploy" / "versions.lock").read_text(encoding="utf-8")) or {}
    images: dict[str, str] = versions.get("images", {}) or {}
    validate_pinned_images(images)
    local_models, external_models = _load_selected_models(root)
    return {
        "requirement": "FR-F6",
        "bundle_dir": bundle_dir,
        "images": [
            {"name": name, "ref": ref, "tar": f"images/{name}.tar"}
            for name, ref in images.items()
        ],
        "models": local_models,
        "external_models": external_models,
        "docs": _docs(root),
    }


def render_airgap_runbook(manifest: dict[str, Any]) -> str:
    """Render operator commands for producing an air-gapped bundle."""
    bundle_dir = manifest["bundle_dir"]
    lines = [
        "# E2EAIDEV air-gapped bundle plan",
        "",
        "This FR-F6 plan is secret-free. Run it on an internet-connected staging machine, then copy the bundle to the offline install host.",
        "",
        "## 1. Prepare directories",
        f"mkdir -p {bundle_dir}/images {bundle_dir}/models {bundle_dir}/docs",
        "",
        "## 2. Container images",
    ]
    for image in manifest["images"]:
        lines.append(f"docker pull {image['ref']}")
        lines.append(f"docker save -o {bundle_dir}/{image['tar']} {image['ref']}")
    lines.extend(["", "## 3. Model mirror"])
    if manifest["models"]:
        for model in manifest["models"]:
            source = model["source"]
            if model["served_by"] == "ollama":
                lines.append(f"ollama pull {source}")
                lines.append(f"ollama show {source} --modelfile > {bundle_dir}/{model['mirror_path']}.Modelfile")
            else:
                lines.append(f"# Mirror {source} for {model['served_by']} into {bundle_dir}/{model['mirror_path']}")
    else:
        lines.append("# No local models selected yet; run `uv run e2eai models` before building the final offline bundle.")
    if manifest["external_models"]:
        lines.append("# External API models are listed for configuration only; no provider keys are included in the offline bundle.")
    lines.extend(["", "## 4. Offline documentation"])
    if manifest["docs"]:
        for doc in manifest["docs"]:
            lines.append(f"cp --parents {doc} {bundle_dir}/docs/")
    else:
        lines.append("# No docs/ files found.")
    lines.extend([
        "",
        "## 5. Pack bundle",
        f"tar -czf {bundle_dir}.tar.gz -C {Path(bundle_dir).parent or Path('.')} {Path(bundle_dir).name}",
    ])
    return "\n".join(lines) + "\n"
