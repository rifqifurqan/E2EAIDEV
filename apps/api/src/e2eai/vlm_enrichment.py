"""Optional VLM enrichment boundary (FR-D15).

This module is deterministic/offline: it decides which parsed pages should be sent to a
vision-language model later, builds the async job plan, and normalizes derived VLM output. It never
stores credentials or expands document permissions per user; VLM chunks inherit the source document's
permission model by document/version linkage.
"""

from collections.abc import Sequence

VLM_DERIVED_LABEL = "AI-described from figure"


def select_vlm_pages(
    pages: Sequence[dict],
    *,
    low_confidence_threshold: float = 0.7,
    figure_heavy_threshold: int = 2,
) -> list[dict]:
    """Select only flagged pages for optional VLM enrichment (FR-D15 routing).

    Pages are selected when baseline parsing has low confidence, the page is figure-heavy, or an
    admin/folder policy explicitly forces VLM. Output is safe routing metadata only.
    """
    selected: list[dict] = []
    for raw in pages:
        page = int(raw.get("page") or 0)
        if page <= 0:
            continue
        parse_confidence = raw.get("parse_confidence")
        figure_count = int(raw.get("figure_count") or 0)
        reasons: list[str] = []
        if parse_confidence is not None and float(parse_confidence) < low_confidence_threshold:
            reasons.append("low_confidence_parse")
        if figure_count >= figure_heavy_threshold:
            reasons.append("figure_heavy")
        if bool(raw.get("force_vlm")):
            reasons.append("forced_by_policy")
        if not reasons:
            continue
        entry = {"page": page, "reasons": reasons}
        if parse_confidence is not None:
            entry["parse_confidence"] = float(parse_confidence)
        entry["figure_count"] = figure_count
        selected.append(entry)
    return sorted(selected, key=lambda row: row["page"])


def build_vlm_enrichment_plan(
    *,
    document_id: str,
    version_id: str,
    selected_pages: Sequence[dict],
    enabled: bool,
) -> dict:
    """Build the async VLM enrichment job plan without running a model (FR-D15)."""
    safe_pages = [{"page": int(row["page"]), "reasons": list(row.get("reasons") or [])} for row in selected_pages]
    return {
        "enabled": bool(enabled),
        "enqueue": bool(enabled and safe_pages),
        "job_type": "vlm_enrich",
        "document_id": str(document_id),
        "version_id": str(version_id),
        "pages": safe_pages if enabled else [],
        "derived_content": {
            "label": VLM_DERIVED_LABEL,
            "permission_inheritance": "document",
            "egress_policy_applies": True,
        },
    }


def build_vlm_derived_chunks(*, document_id: str, version_id: str, outputs: Sequence[dict]) -> list[dict]:
    """Normalize VLM outputs into derived chunks labeled for user confirmation (FR-D15).

    Only source linkage, page, figure object key, derived text, and permission inheritance metadata are
    returned. Provider request metadata, tokens, keys, and raw credential fields are deliberately not copied.
    """
    chunks: list[dict] = []
    for raw in outputs:
        text = str(raw.get("text") or "").strip()
        if not text:
            continue
        chunks.append({
            "document_id": str(document_id),
            "version_id": str(version_id),
            "kind": "vlm",
            "page": int(raw.get("page") or 0) or None,
            "label": VLM_DERIVED_LABEL,
            "text": text,
            "figure_object_key": raw.get("figure_object_key"),
            "permissions": {"inherits_from": "document", "source_document_id": str(document_id)},
        })
    return chunks


async def run_vlm_enrichment(plan: dict, client) -> dict:
    """Run the optional VLM job; an outage degrades instead of failing ingestion (NFR-19).

    ``client.describe_page(document_id=, version_id=, page=)`` returns ``{"text", "figure_object_key"}``.
    The baseline parse is already indexed, so on the first upstream error the remaining pages are
    skipped (fail fast) and reported as ``failed_pages``. Errors are reduced to the reason code
    ``vlm_unavailable``: hosts, URLs, keys and exception text are never copied into the result.
    """
    if not plan.get("enqueue"):
        return {"status": "skipped", "chunks": [], "failed_pages": [], "reason": None}
    pages = [int(row["page"]) for row in plan.get("pages") or []]
    outputs: list[dict] = []
    failed: list[int] = []
    for index, page in enumerate(pages):
        try:
            result = await client.describe_page(
                document_id=plan["document_id"], version_id=plan["version_id"], page=page,
            )
        except Exception:  # noqa: BLE001 - any upstream failure degrades; details are intentionally dropped
            failed.extend(pages[index:])
            break
        outputs.append({
            "page": page, "text": (result or {}).get("text"),
            "figure_object_key": (result or {}).get("figure_object_key"),
        })
    chunks = build_vlm_derived_chunks(document_id=plan["document_id"], version_id=plan["version_id"], outputs=outputs)
    return {
        "status": "degraded" if failed else "ok",
        "chunks": chunks, "failed_pages": failed,
        "reason": "vlm_unavailable" if failed else None,
    }
