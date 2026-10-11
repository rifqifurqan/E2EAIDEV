"""Combined document + live system citations (FR-X6).

Answers can combine documents and live data, with citations for both:
- Document citations: source=document, document title, page, section
- Live system citations: source=live_system, system_id, operation_id

Only executed tool calls appear as live citations; skipped, rejected,
and denied tool calls are excluded. Safe output only — no raw tokens,
server URLs, credentials, or request/response payloads in citations.
"""

from __future__ import annotations


_EXECUTED_STATUSES = frozenset({"executed", "confirmed_executed"})

_RECORD_ID_KEYS = ("record_id", "system_record_id", "id", "order_id", "employee_id")


def _extract_record_id(tool_call: dict) -> str | None:
    """Extract a safe system record id from an executed tool-call summary.

    The citation may identify the system record used by the answer, but it must
    not expose raw payloads or auth material. Prefer explicit record_id fields;
    fall back to common safe id-like keys inside the sanitized result summary.
    """
    for key in _RECORD_ID_KEYS:
        value = tool_call.get(key)
        if value not in (None, ""):
            return str(value)
    safe_result = tool_call.get("safe_result")
    if isinstance(safe_result, dict):
        for key in _RECORD_ID_KEYS:
            value = safe_result.get(key)
            if value not in (None, ""):
                return str(value)
    return None


def build_combined_citations(
    *,
    doc_citations: list[dict],
    tool_call_results: list[dict],
) -> list[dict]:
    """Merge document citations and live MCP tool-call results into a unified list.

    Document citations get ``source: "document"``; live tool-call results get
    ``source: "live_system"`` with system_id and operation_id. Only executed
    tool calls are included — skipped/rejected/denied are excluded.

    No raw tokens, server URLs, credentials, or request/response payloads
    appear in the output.
    """
    combined: list[dict] = []

    for cite in doc_citations:
        combined.append({
            "source": "document",
            "document": cite.get("document", ""),
            "page": cite.get("page"),
            "section": cite.get("section"),
        })

    for tc in tool_call_results:
        if tc.get("status") not in _EXECUTED_STATUSES:
            continue
        citation = {
            "source": "live_system",
            "system_id": tc.get("system_id", ""),
            "operation_id": tc.get("operation_id", ""),
        }
        record_id = _extract_record_id(tc)
        if record_id:
            citation["record_id"] = record_id
        combined.append(citation)

    return combined
