"""P1 Top unanswered questions report for knowledge owners (FR-I2).

Tests compute_top_unanswered_report() — a deterministic/offline helper that
aggregates unanswered topic buckets from usage events into a knowledge-gap
report, helping knowledge owners identify which documents are missing.

All outputs are safe: only aggregate metrics, topic bucket labels, IDs, and
counts — never raw prompts, question text, answers, document text, titles,
snippets, secrets, tokens, or credentials.
"""

import json

from e2eai.top_unanswered import compute_top_unanswered_report


# ---------- Sample usage event data for tests ----------

_USAGE_EVENTS = [
    # Answered — should NOT appear in unanswered gap report
    {"user_id": "u1", "division_id": "d1", "answered": True,  "topic": "leave-policy"},
    {"user_id": "u2", "division_id": "d2", "answered": True,  "topic": "payslip"},
    # Unanswered — should drive the gap report
    {"user_id": "u1", "division_id": "d1", "answered": False, "topic": "vpn-setup"},
    {"user_id": "u2", "division_id": "d1", "answered": False, "topic": "vpn-setup"},
    {"user_id": "u3", "division_id": "d2", "answered": False, "topic": "vpn-setup"},
    {"user_id": "u2", "division_id": "d2", "answered": False, "topic": "expense-report"},
    {"user_id": "u3", "division_id": "d2", "answered": False, "topic": "expense-report"},
    {"user_id": "u4", "division_id": "d3", "answered": False, "topic": "travel-policy"},
]


# ---------- 1. report contains all expected top-level keys ----------

def test_top_unanswered_report_contains_expected_keys():
    """compute_top_unanswered_report returns all FR-I2 knowledge-gap keys."""
    report = compute_top_unanswered_report(_USAGE_EVENTS)

    for key in ("total_unanswered", "unique_topics", "top_unanswered_gaps"):
        assert key in report, f"Missing key '{key}' in knowledge-gap report"


# ---------- 2. total_unanswered counts only unanswered events ----------

def test_total_unanswered_counts_only_unanswered_events():
    """total_unanswered is the count of events with answered=False."""
    report = compute_top_unanswered_report(_USAGE_EVENTS)
    # 6 unanswered events (3 vpn-setup, 2 expense-report, 1 travel-policy)
    assert report["total_unanswered"] == 6


# ---------- 3. answered events are excluded from the gap report ----------

def test_answered_events_excluded_from_gap_report():
    """Topics from answered events must not appear in top_unanswered_gaps."""
    report = compute_top_unanswered_report(_USAGE_EVENTS)
    gap_topics = [g["topic"] for g in report["top_unanswered_gaps"]]

    assert "leave-policy" not in gap_topics, "Answered topic leaked into gap report"
    assert "payslip" not in gap_topics, "Answered topic leaked into gap report"


# ---------- 4. unanswered topics appear sorted by count descending ----------

def test_top_unanswered_topics_sorted_by_count_descending():
    """top_unanswered_gaps is sorted by count descending (highest frequency first)."""
    report = compute_top_unanswered_report(_USAGE_EVENTS)
    gaps = report["top_unanswered_gaps"]

    # vpn-setup(3) > expense-report(2) > travel-policy(1)
    assert gaps[0]["topic"] == "vpn-setup"
    assert gaps[0]["count"] == 3
    assert gaps[1]["topic"] == "expense-report"
    assert gaps[1]["count"] == 2

    # Verify descending order in general
    for i in range(len(gaps) - 1):
        assert gaps[i]["count"] >= gaps[i + 1]["count"], (
            f"Gaps not sorted descending at index {i}"
        )


# ---------- 5. each gap entry has required fields ----------

def test_gap_entry_has_required_fields():
    """Each top_unanswered_gaps entry has topic, count, division_ids, division_count."""
    report = compute_top_unanswered_report(_USAGE_EVENTS)

    for entry in report["top_unanswered_gaps"]:
        assert "topic" in entry, "Missing 'topic' in gap entry"
        assert "count" in entry, "Missing 'count' in gap entry"
        assert "division_ids" in entry, "Missing 'division_ids' in gap entry"
        assert "division_count" in entry, "Missing 'division_count' in gap entry"
        assert isinstance(entry["count"], int)
        assert isinstance(entry["division_ids"], list)
        assert isinstance(entry["division_count"], int)
        assert entry["division_count"] == len(entry["division_ids"])


# ---------- 6. multi-division gap captures all affected divisions ----------

def test_multi_division_gap_captures_all_divisions():
    """A topic asked unanswered in multiple divisions lists all division IDs."""
    report = compute_top_unanswered_report(_USAGE_EVENTS)
    gaps_by_topic = {g["topic"]: g for g in report["top_unanswered_gaps"]}

    # vpn-setup was asked unanswered in d1 and d2
    vpn_gap = gaps_by_topic["vpn-setup"]
    assert set(vpn_gap["division_ids"]) == {"d1", "d2"}
    assert vpn_gap["division_count"] == 2

    # expense-report only in d2
    expense_gap = gaps_by_topic["expense-report"]
    assert set(expense_gap["division_ids"]) == {"d2"}
    assert expense_gap["division_count"] == 1


# ---------- 7. unique_topics counts distinct unanswered topic buckets ----------

def test_unique_topics_counts_distinct_buckets():
    """unique_topics is the number of distinct unanswered topic buckets."""
    report = compute_top_unanswered_report(_USAGE_EVENTS)
    # vpn-setup, expense-report, travel-policy = 3
    assert report["unique_topics"] == 3


# ---------- 8. capped at 20 gaps ----------

def test_top_unanswered_gaps_capped_at_twenty():
    """top_unanswered_gaps returns at most 20 entries."""
    events = [
        {"user_id": "u1", "division_id": "d1", "answered": False, "topic": f"topic-{i}"}
        for i in range(30)
    ]
    report = compute_top_unanswered_report(events)
    assert len(report["top_unanswered_gaps"]) <= 20


# ---------- 9. empty events produce safe zero defaults ----------

def test_empty_events_return_safe_defaults():
    """An empty event list returns zero totals and an empty gap list."""
    report = compute_top_unanswered_report([])

    assert report["total_unanswered"] == 0
    assert report["unique_topics"] == 0
    assert report["top_unanswered_gaps"] == []


# ---------- 10. all-answered events produce empty gap report ----------

def test_all_answered_events_produce_empty_gap_report():
    """When every event is answered, the gap report has no gaps."""
    events = [
        {"user_id": "u1", "division_id": "d1", "answered": True, "topic": "some-doc"},
        {"user_id": "u2", "division_id": "d2", "answered": True, "topic": "other-doc"},
    ]
    report = compute_top_unanswered_report(events)

    assert report["total_unanswered"] == 0
    assert report["top_unanswered_gaps"] == []


# ---------- 11. unsafe topic labels are redacted ----------

def test_unsafe_topic_labels_are_redacted():
    """Topic labels containing secrets/credentials are redacted to 'redacted'
    so raw sensitive text never leaks into the knowledge-gap report."""
    events = [
        {"user_id": "u1", "division_id": "d1", "answered": False,
         "topic": "secret API key production bearer token"},
        {"user_id": "u2", "division_id": "d2", "answered": False,
         "topic": "normal-gap-topic"},
    ]
    report = compute_top_unanswered_report(events)
    serialized = json.dumps(report).lower()

    for forbidden in ("secret", "api key", "production", "bearer", "token"):
        assert forbidden not in serialized, (
            f"Forbidden term '{forbidden}' found in knowledge-gap report"
        )

    gap_topics = [g["topic"] for g in report["top_unanswered_gaps"]]
    assert "redacted" in gap_topics
    assert "normal-gap-topic" in gap_topics


# ---------- 12. no raw prompts or secrets in output ----------

def test_no_raw_prompts_or_secrets_in_output():
    """The report must contain only safe aggregate data — never raw question text,
    answers, document text, secrets, tokens, titles, or credentials."""
    events = [
        {"user_id": "u1", "division_id": "d1",
         "question": "What is the WhatsApp revenue share? Bearer token abc123",
         "answer": "The revenue share is confidential",
         "answered": False,
         "topic": "partnership"},
    ]
    report = compute_top_unanswered_report(events)
    serialized = json.dumps(report).lower()

    for forbidden in ("whatsapp", "revenue share", "bearer", "abc123",
                      "confidential", "prompt", "password", "credential"):
        assert forbidden not in serialized, (
            f"Forbidden term '{forbidden}' found in knowledge-gap report output"
        )


# ---------- 13. missing optional fields default gracefully ----------

def test_missing_optional_fields_default_gracefully():
    """Events with missing answered/topic/division_id fields produce valid output."""
    events = [
        {"user_id": "u1"},              # no answered → treated as unanswered
        {"user_id": "u2", "answered": False},  # no topic → defaults to "unknown"
    ]
    report = compute_top_unanswered_report(events)

    assert report["total_unanswered"] >= 1
    assert isinstance(report["top_unanswered_gaps"], list)


# ---------- 14. tied counts are ranked by breadth ----------

def test_tied_counts_rank_more_affected_divisions_first():
    """When topics have the same unanswered count, the report ranks the topic affecting
    more divisions first so knowledge owners see the broadest missing-document gap."""
    events = [
        {"user_id": "u1", "division_id": "d1", "answered": False, "topic": "single-division"},
        {"user_id": "u2", "division_id": "d1", "answered": False, "topic": "single-division"},
        {"user_id": "u3", "division_id": "d1", "answered": False, "topic": "multi-division"},
        {"user_id": "u4", "division_id": "d2", "answered": False, "topic": "multi-division"},
    ]

    report = compute_top_unanswered_report(events)

    assert report["top_unanswered_gaps"][0]["topic"] == "multi-division"
    assert report["top_unanswered_gaps"][0]["division_count"] == 2


# ---------- 15. API route wiring ----------

def test_top_unanswered_api_route_is_wired():
    """The POST /api/v1/improve/top-unanswered endpoint exists in the FastAPI app."""
    from e2eai.main import app

    openapi = app.openapi()
    assert "/api/v1/improve/top-unanswered" in openapi["paths"], (
        "FR-I2 endpoint /api/v1/improve/top-unanswered not found in OpenAPI spec"
    )
