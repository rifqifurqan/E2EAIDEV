"""Technical and maintenance manual structure helpers (FR-D16).

Pure/offline utilities preserve links between procedure steps, figures, part/spec tables, and safety
warnings. Answer contexts require safety warnings verbatim and flag figure-only numeric values for user
confirmation.
"""

import re
from collections.abc import Sequence

_FIG_REF_RE = re.compile(r"\b(?:Fig\.|Figure)\s*\d+(?:[-.]\d+)?\b", re.IGNORECASE)
_SPEC_KEYS = {"torque", "pressure", "clearance", "temperature", "voltage", "current"}


def _canonical_ref(ref: str) -> str:
    ref = " ".join(str(ref or "").strip().split())
    if ref.lower().startswith("figure "):
        ref = "Fig. " + ref.split(" ", 1)[1]
    return ref


def _figure_refs(text: str) -> list[str]:
    seen: list[str] = []
    for match in _FIG_REF_RE.findall(text):
        ref = _canonical_ref(match)
        if ref not in seen:
            seen.append(ref)
    return seen


def _add_table_facts(procedure: dict, block: dict) -> None:
    source = f"table:{block.get('title') or 'unnamed'}"
    for row in block.get("rows") or []:
        if row.get("part_no"):
            part = {"part_no": str(row["part_no"]), "source": source}
            if part not in procedure["parts"]:
                procedure["parts"].append(part)
        for key, value in row.items():
            normalized = str(key).strip().lower()
            if normalized in _SPEC_KEYS and value:
                spec = {"name": normalized, "value": str(value), "source": source}
                if spec not in procedure["specs"]:
                    procedure["specs"].append(spec)


def extract_manual_procedure(blocks: Sequence[dict], *, procedure_id: str) -> dict:
    """Extract a procedure skeleton preserving figures, tables, specs, and verbatim warnings."""
    procedure = {
        "procedure_id": procedure_id,
        "title": "",
        "warnings": [],
        "steps": [],
        "figures": {},
        "parts": [],
        "specs": [],
    }
    for block in blocks:
        kind = str(block.get("kind") or "").lower()
        text = str(block.get("text") or "").strip()
        if kind == "heading" and not procedure["title"]:
            procedure["title"] = text
        elif kind == "safety_warning" and text:
            procedure["warnings"].append({"level": str(block.get("level") or "WARNING"), "text": text})
        elif kind == "step" and text:
            procedure["steps"].append({"text": text, "figure_refs": _figure_refs(text)})
        elif kind == "figure":
            ref = _canonical_ref(block.get("ref") or block.get("id") or "")
            if ref:
                procedure["figures"][ref] = {
                    "caption": str(block.get("caption") or ""),
                    "object_key": block.get("object_key"),
                }
        elif kind == "table":
            _add_table_facts(procedure, block)
    return procedure


def build_manual_answer_context(procedure: dict) -> dict:
    """Build answer constraints so FR-D16 warnings/specs are quoted safely."""
    citation_targets: list[str] = []
    for step in procedure.get("steps") or []:
        for ref in step.get("figure_refs") or []:
            target = f"figure:{ref}"
            if target not in citation_targets:
                citation_targets.append(target)
    for row in (procedure.get("parts") or []) + (procedure.get("specs") or []):
        source = row.get("source")
        if source and source not in citation_targets:
            citation_targets.append(source)
    figure_confirmation_required = [
        spec for spec in procedure.get("specs") or []
        if str(spec.get("source") or "").startswith("figure:")
    ]
    return {
        "procedure_id": procedure.get("procedure_id"),
        "title": procedure.get("title"),
        "required_verbatim_warnings": [w["text"] for w in procedure.get("warnings") or [] if w.get("text")],
        "steps": procedure.get("steps") or [],
        "parts": procedure.get("parts") or [],
        "specs": procedure.get("specs") or [],
        "citation_targets": citation_targets,
        "figure_confirmation_required": figure_confirmation_required,
    }
