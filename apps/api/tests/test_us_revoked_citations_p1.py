"""FR-C7 Chat history after access revocation hides revoked citations safely."""

from e2eai.revoked_citations import (
    build_revoked_citation_audit,
    classify_removed_citations,
    sanitize_citations_for_history,
)


def test_revoked_citation_replaced_with_safe_notice_without_revealing_restricted_title():
    citations = [
        {"document_id": "doc-1", "document": "WhatsApp Partnership", "page": 4, "section": "terms"},
        {"document_id": "doc-2", "document": "Secret Project", "page": 7, "section": "budget"},
        {"document_id": "doc-3", "document": "Team Notes", "page": 2, "section": "plan"},
    ]

    sanitized = sanitize_citations_for_history(
        citations,
        accessible_ids={"WhatsApp Partnership", "Team Notes"},
        accessible_doc_ids={"doc-1", "doc-3"},
    )

    assert sanitized == [
        {"document": "WhatsApp Partnership", "page": 4, "section": "terms"},
        {"notice": "source no longer accessible", "page": 7},
        {"document": "Team Notes", "page": 2, "section": "plan"},
    ]


def test_classify_removed_citations_counts_without_disclosing_titles():
    citations = [
        {"document_id": "doc-1", "document": "Public Report", "page": 1},
        {"document_id": "doc-2", "document": "Restricted Doc", "page": 3},
    ]
    result = classify_removed_citations(
        citations,
        accessible_ids={"Public Report"},
        accessible_doc_ids={"doc-1"},
    )
    assert len(result["kept"]) == 1
    assert result["kept"][0]["document"] == "Public Report"
    assert result["removed_count"] == 1
    assert result["removed"][0]["notice"] == "source no longer accessible"
    assert "Restricted Doc" not in str(result["removed"])


def test_build_revoked_citation_audit_is_safe_metadata_only():
    removed = [{"notice": "source no longer accessible", "page": 7}]
    audit = build_revoked_citation_audit(removed)
    assert audit == {"hidden_citations": 1, "reasons": ["source no longer accessible"]}


def test_sanitize_handles_empty_and_fully_revoked():
    assert sanitize_citations_for_history([], accessible_ids=set(), accessible_doc_ids=set()) == []
    citations = [{"document_id": "doc-1", "document": "Only Doc", "page": 1}]
    sanitized = sanitize_citations_for_history(citations, accessible_ids=set(), accessible_doc_ids=set())
    assert sanitized == [{"notice": "source no longer accessible", "page": 1}]
