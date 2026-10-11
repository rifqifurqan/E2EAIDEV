"""FR-C7 Chat history hides revoked citations with source-no-longer-accessible notice.

Pure/offline helpers: classify removed citations, and produce a sanitized citation list that
replaces any revoked/cached-removed citation with a safe notice (FR-C7). No restricted titles or
content are ever revealed — only a count and a notice per removed citation.
"""

from collections.abc import Sequence


def classify_removed_citations(
    citations: Sequence[dict],
    *,
    accessible_ids: set[str],
    accessible_doc_ids: set[str],
) -> dict:
    """Split citations into kept vs removed-by-access-revocation (FR-C7).

    A citation is considered removed if its source document is no longer accessible to the user
    (`document_id` or `document` title not in the accessible sets). Output exposes only a count and
    safe notice fields — never restricted document titles or snippets.
    """
    kept: list[dict] = []
    removed: list[dict] = []
    for citation in citations:
        doc_id = str(citation.get("document_id") or "")
        doc_title = str(citation.get("document") or "")
        if doc_id and doc_id in accessible_doc_ids:
            kept.append(citation)
            continue
        if doc_title and doc_title in accessible_ids:
            kept.append(citation)
            continue
        removed.append({
            "notice": "source no longer accessible",
            "page": citation.get("page"),
        })
    return {"kept": kept, "removed": removed, "removed_count": len(removed)}


def sanitize_citations_for_history(
    citations: Sequence[dict],
    *,
    accessible_ids: set[str],
    accessible_doc_ids: set[str],
) -> list[dict]:
    """Return citations safe to surface for a user after a share revokes mid-conversation (FR-C7).

    Revoked citations are replaced with a safe notice in position; accessible ones are echoed as-is so
    the UI can still highlight them. Restricted document titles are never disclosed.
    """
    visible: list[dict] = []
    for citation in citations:
        doc_id = str(citation.get("document_id") or "")
        doc_title = str(citation.get("document") or "")
        if (doc_id and doc_id in accessible_doc_ids) or (doc_title and doc_title in accessible_ids):
            visible.append({"document": citation.get("document"), "page": citation.get("page"), "section": citation.get("section")})
        else:
            visible.append({"notice": "source no longer accessible", "page": citation.get("page")})
    return visible


def build_revoked_citation_audit(removed: Sequence[dict]) -> dict:
    """Safe audit metadata for hidden citations (never includes restricted titles)."""
    return {
        "hidden_citations": len(removed),
        "reasons": [str(row.get("notice")) for row in removed],
    }
