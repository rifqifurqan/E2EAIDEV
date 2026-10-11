"""FR-D15 Optional VLM add-on routing and derived-output labeling."""

from e2eai.vlm_enrichment import (
    VLM_DERIVED_LABEL,
    build_vlm_derived_chunks,
    build_vlm_enrichment_plan,
    select_vlm_pages,
)


def test_vlm_routing_selects_only_flagged_or_figure_heavy_pages_with_reasons():
    pages = [
        {"page": 1, "parse_confidence": 0.96, "figure_count": 0},
        {"page": 2, "parse_confidence": 0.54, "figure_count": 0},
        {"page": 3, "parse_confidence": 0.91, "figure_count": 3},
        {"page": 4, "parse_confidence": 0.88, "figure_count": 0, "force_vlm": True},
    ]

    selected = select_vlm_pages(pages, low_confidence_threshold=0.7, figure_heavy_threshold=2)

    assert [row["page"] for row in selected] == [2, 3, 4]
    reasons = {row["page"]: row["reasons"] for row in selected}
    assert reasons[2] == ["low_confidence_parse"]
    assert reasons[3] == ["figure_heavy"]
    assert reasons[4] == ["forced_by_policy"]
    assert "parse_confidence" in selected[0]
    assert "figure_count" in selected[1]


def test_vlm_enrichment_plan_is_async_and_inherits_document_permissions_without_principal_expansion():
    plan = build_vlm_enrichment_plan(
        document_id="doc-123",
        version_id="ver-456",
        selected_pages=[
            {"page": 7, "reasons": ["figure_heavy"], "figure_count": 2},
            {"page": 9, "reasons": ["low_confidence_parse"], "parse_confidence": 0.4},
        ],
        enabled=True,
    )

    assert plan == {
        "enabled": True,
        "enqueue": True,
        "job_type": "vlm_enrich",
        "document_id": "doc-123",
        "version_id": "ver-456",
        "pages": [
            {"page": 7, "reasons": ["figure_heavy"]},
            {"page": 9, "reasons": ["low_confidence_parse"]},
        ],
        "derived_content": {
            "label": VLM_DERIVED_LABEL,
            "permission_inheritance": "document",
            "egress_policy_applies": True,
        },
    }
    serialized = str(plan)
    assert "user:" not in serialized
    assert "team:" not in serialized
    assert "viewer" not in serialized


def test_vlm_derived_chunks_are_labeled_and_linked_to_source_version_without_secrets():
    chunks = build_vlm_derived_chunks(
        document_id="doc-123",
        version_id="ver-456",
        outputs=[
            {"page": 4, "text": "Diagram shows pump P-100 connected to valve V-7.", "figure_object_key": "sha256/fig-4.png"},
            {"page": 5, "text": "Chart series A rises from 10 to 15.", "figure_object_key": "sha256/chart-5.png", "api_key": "sk-secret"},
        ],
    )

    assert chunks == [
        {
            "document_id": "doc-123",
            "version_id": "ver-456",
            "kind": "vlm",
            "page": 4,
            "label": VLM_DERIVED_LABEL,
            "text": "Diagram shows pump P-100 connected to valve V-7.",
            "figure_object_key": "sha256/fig-4.png",
            "permissions": {"inherits_from": "document", "source_document_id": "doc-123"},
        },
        {
            "document_id": "doc-123",
            "version_id": "ver-456",
            "kind": "vlm",
            "page": 5,
            "label": VLM_DERIVED_LABEL,
            "text": "Chart series A rises from 10 to 15.",
            "figure_object_key": "sha256/chart-5.png",
            "permissions": {"inherits_from": "document", "source_document_id": "doc-123"},
        },
    ]
    assert "sk-secret" not in str(chunks)
