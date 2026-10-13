"""License report for the tools and models chosen at install time (NFR-17).

The wizard shows this before it writes any file, so the operator sees the license of every tool and model first.
Tool licenses below were entered from general knowledge of each project, NOT re-checked against upstream at build time:
the report says so, and PRD §17.6 requires re-verification before each release. Model licenses come from
`catalog/models.yaml`. External API models are governed by the provider's terms, not a license we can summarise.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import models
from .services import BY_NAME, enabled_services


@dataclass(frozen=True)
class ToolLicense:
    label: str
    spdx: str
    license_class: str  # permissive | copyleft-separate | restrictive
    note: str = ""


# Only permissive or separate-service tools are used. AGPL tools would be `copyleft-separate` and run as their own service.
TOOL_LICENSES: dict[str, ToolLicense] = {
    "postgres": ToolLicense("PostgreSQL + pgvector", "PostgreSQL", "permissive", "pgvector also uses the PostgreSQL license"),
    "valkey": ToolLicense("Valkey", "BSD-3-Clause", "permissive", "chosen over Redis 8 (AGPL/RSAL/SSPL)"),
    "openfga": ToolLicense("OpenFGA", "Apache-2.0", "permissive"),
    "seaweedfs": ToolLicense("SeaweedFS", "Apache-2.0", "permissive"),
    "litellm": ToolLicense("LiteLLM", "MIT", "permissive", "the separate enterprise directory is not used"),
    "ollama": ToolLicense("Ollama", "MIT", "permissive"),
    "vllm": ToolLicense("vLLM", "Apache-2.0", "permissive"),
    "tei-embed": ToolLicense("Text Embeddings Inference", "Apache-2.0", "permissive"),
    "tei-rerank": ToolLicense("Text Embeddings Inference", "Apache-2.0", "permissive"),
    "keycloak": ToolLicense("Keycloak", "Apache-2.0", "permissive"),
}

_REVERIFY = ("Tool licenses were entered from general knowledge and not re-checked against upstream at build time; "
             "re-verify them before each release (PRD 17.6).")


def license_report(a: dict, catalog: dict[str, models.Model]) -> list[dict]:
    """One row per enabled tool and chosen model: kind, name, license, whether a human should review it."""
    rows: list[dict] = []
    for name in enabled_services(a):
        info = TOOL_LICENSES.get(name)
        if info is None:
            rows.append({"kind": "tool", "name": name, "label": BY_NAME[name].label, "license": "unknown",
                         "license_class": "unknown", "review": True, "note": "no license entry; add one before install"})
            continue
        rows.append({"kind": "tool", "name": name, "label": info.label, "license": info.spdx,
                     "license_class": info.license_class, "review": info.license_class != "permissive",
                     "note": info.note})
    chosen = a.get("models") or {}
    for role in models.ROLES:
        for model_id in chosen.get(role, []):
            m = catalog[model_id]
            warning = models.license_warning(m)
            rows.append({"kind": "model", "name": m.id, "label": f"{m.id} ({role})", "license": m.license,
                         "license_class": m.license_class, "review": warning is not None, "note": warning or ""})
    for ext in chosen.get("external", []):
        prefix = models.EXTERNAL_PROVIDERS[ext["provider"]][0]
        rows.append({"kind": "external-model", "name": f"{prefix}/{ext['model']}", "label": f"{ext['provider']} {ext['model']}",
                     "license": "provider terms", "license_class": "external", "review": True,
                     "note": "Governed by the provider terms of service; data leaves this machine (FR-M9)"})
    return rows


def catalog_license_report(catalog: dict[str, models.Model]) -> list[dict]:
    """Everything the wizard can install (all tools, all catalog models), independent of the machine."""
    rows = [{"kind": "tool", "name": n, "label": i.label, "license": i.spdx, "license_class": i.license_class,
             "review": i.license_class != "permissive", "note": i.note} for n, i in TOOL_LICENSES.items()]
    for m in catalog.values():
        warning = models.license_warning(m)
        rows.append({"kind": "model", "name": m.id, "label": f"{m.id} ({m.role})", "license": m.license,
                     "license_class": m.license_class, "review": warning is not None, "note": warning or ""})
    return rows


def render_license_report(rows: list[dict]) -> str:
    lines = ["License report (NFR-17)", ""]
    for r in rows:
        flag = "REVIEW" if r["review"] else "ok"
        note = f" - {r['note']}" if r["note"] else ""
        lines.append(f"[{flag}] {r['kind']}: {r['label']} -> {r['license']} ({r['license_class']}){note}")
    lines += ["", _REVERIFY]
    return "\n".join(lines) + "\n"
