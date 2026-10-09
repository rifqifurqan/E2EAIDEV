"""Lab tool catalog with license warnings (FR-L3)."""

from __future__ import annotations

from dataclasses import asdict, dataclass


WARNING_LICENSE_MARKERS = ("agpl", "elv2", "elastic license", "non-commercial", "noncommercial", "cc-by-nc")


@dataclass(frozen=True)
class ToolEntry:
    id: str
    name: str
    category: str
    license: str
    maturity: str
    resource_need: str
    description: str


TOOL_CATALOG: tuple[ToolEntry, ...] = (
    ToolEntry(
        id="ragas",
        name="Ragas",
        category="evaluation",
        license="Apache-2.0",
        maturity="stable",
        resource_need="low",
        description="RAG quality metrics and synthetic test data adapter.",
    ),
    ToolEntry(
        id="deepeval",
        name="DeepEval",
        category="evaluation",
        license="Apache-2.0",
        maturity="maturing",
        resource_need="low",
        description="LLM evaluation framework with bias, hallucination, and correctness metrics.",
    ),
    ToolEntry(
        id="phoenix",
        name="Arize Phoenix",
        category="observability",
        license="ELv2 / Apache components",
        maturity="stable",
        resource_need="medium",
        description="Traces, evals, and LLM observability for experiments and production runs.",
    ),
    ToolEntry(
        id="promptfoo",
        name="promptfoo",
        category="red-team",
        license="MIT",
        maturity="stable",
        resource_need="low",
        description="Prompt regression tests, red-team probes, and CI-friendly eval cases.",
    ),
    ToolEntry(
        id="inspect-ai",
        name="Inspect AI",
        category="evaluation",
        license="MIT",
        maturity="maturing",
        resource_need="medium",
        description="Evaluation framework for model behavior and benchmark tasks.",
    ),
    ToolEntry(
        id="label-studio",
        name="Label Studio",
        category="annotation",
        license="Apache-2.0 / Enterprise features",
        maturity="stable",
        resource_need="medium",
        description="Human labeling and review workflows for gold datasets.",
    ),
    ToolEntry(
        id="garak",
        name="garak",
        category="security",
        license="Apache-2.0",
        maturity="maturing",
        resource_need="medium",
        description="LLM vulnerability scanner for prompt injection and unsafe behavior probes.",
    ),
    ToolEntry(
        id="noncommercial-synth",
        name="Example Non-commercial Synthesizer",
        category="synthetic-data",
        license="CC-BY-NC-4.0 non-commercial",
        maturity="experimental",
        resource_need="high",
        description="Placeholder catalog row showing how non-commercial model/tool warnings appear.",
    ),
)


def license_warning(license_name: str) -> bool:
    lower = license_name.lower()
    return any(marker in lower for marker in WARNING_LICENSE_MARKERS)


def warning_text(license_name: str) -> str | None:
    if not license_warning(license_name):
        return None
    lower = license_name.lower()
    if "agpl" in lower:
        return "AGPL tools must run as a separate service and need legal review before install."
    if "elv2" in lower or "elastic license" in lower:
        return "ELv2/Elastic-licensed tools need license review before production use."
    return "Non-commercial tools/models need license review and are blocked from commercial production use."


def tool_catalog(*, installed: set[str] | None = None) -> dict:
    installed = installed or set()
    rows = []
    for entry in TOOL_CATALOG:
        row = asdict(entry)
        row["installed"] = entry.id in installed
        row["status"] = "installed" if row["installed"] else "available"
        row["license_warning"] = license_warning(entry.license)
        row["warning"] = warning_text(entry.license)
        rows.append(row)
    return {
        "tools": rows,
        "summary": {
            "available": len(rows),
            "installed": sum(1 for row in rows if row["installed"]),
            "license_warnings": sum(1 for row in rows if row["license_warning"]),
        },
    }
