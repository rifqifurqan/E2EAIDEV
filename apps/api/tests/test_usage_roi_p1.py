"""P1 Usage and ROI analytics (FR-O7).

Computes active users, questions per division, answer rate, deflection count/rate,
top unanswered topics, and estimated time saved from usage event dictionaries.
Outputs are safe: only aggregate metrics, IDs, and topic strings — never raw
prompts, answers, document text, secrets, tokens, or credentials.
"""

import json

from e2eai.usage_roi import compute_usage_roi_report


# ---------- Sample usage event data for tests ----------

_USAGE_EVENTS = [
    {"user_id": "u1", "division_id": "d1", "question": "How to reset password?", "answered": True, "deflected": False, "topic": "password-reset", "time_saved_minutes": 5},
    {"user_id": "u1", "division_id": "d1", "question": "What is the leave policy?", "answered": True, "deflected": False, "topic": "leave-policy", "time_saved_minutes": 10},
    {"user_id": "u2", "division_id": "d1", "question": "How to configure VPN?", "answered": False, "deflected": False, "topic": "vpn-setup", "time_saved_minutes": 0},
    {"user_id": "u2", "division_id": "d2", "question": "Where is the org chart?", "answered": True, "deflected": True, "topic": "org-chart", "time_saved_minutes": 3},
    {"user_id": "u3", "division_id": "d2", "question": "How to submit expense report?", "answered": False, "deflected": False, "topic": "expense-report", "time_saved_minutes": 0},
    {"user_id": "u3", "division_id": "d2", "question": "What is the travel policy?", "answered": False, "deflected": True, "topic": "travel-policy", "time_saved_minutes": 0},
    {"user_id": "u1", "division_id": "d1", "question": "How to reset password again?", "answered": True, "deflected": False, "topic": "password-reset", "time_saved_minutes": 5},
    {"user_id": "u4", "division_id": "d2", "question": "How to access payslip?", "answered": True, "deflected": False, "topic": "payslip", "time_saved_minutes": 8},
]


# ---------- 1. report contains all expected top-level keys ----------

def test_report_contains_all_expected_keys():
    """compute_usage_roi_report returns all FR-O7 metrics."""
    report = compute_usage_roi_report(_USAGE_EVENTS)

    for key in ("active_users", "total_questions", "questions_per_division",
                "answer_rate", "deflection_count", "deflection_rate",
                "top_unanswered_topics", "estimated_time_saved_minutes"):
        assert key in report, f"Missing key '{key}' in report"


# ---------- 2. active_users counts distinct user_ids ----------

def test_active_users_counts_distinct_users():
    """active_users is the count of distinct user_id values."""
    report = compute_usage_roi_report(_USAGE_EVENTS)
    assert report["active_users"] == 4  # u1, u2, u3, u4


# ---------- 3. total_questions is count of events ----------

def test_total_questions_is_event_count():
    """total_questions equals the number of input events."""
    report = compute_usage_roi_report(_USAGE_EVENTS)
    assert report["total_questions"] == 8


# ---------- 4. questions_per_division groups correctly ----------

def test_questions_per_division_groups_correctly():
    """questions_per_division aggregates event counts by division_id."""
    report = compute_usage_roi_report(_USAGE_EVENTS)

    by_div = {d["division_id"]: d["count"] for d in report["questions_per_division"]}
    # d1: events for u1(3) + u2(1 in d1) = 4; d2: u2(1 in d2) + u3(2) + u4(1) = 4
    assert by_div["d1"] == 4
    assert by_div["d2"] == 4


# ---------- 5. answer_rate is fraction of answered events ----------

def test_answer_rate_is_fraction_of_answered():
    """answer_rate = answered_count / total_questions."""
    report = compute_usage_roi_report(_USAGE_EVENTS)
    # answered: 5 out of 8
    assert report["answer_rate"] == round(5 / 8, 4)


# ---------- 6. deflection_count and rate ----------

def test_deflection_count_and_rate():
    """deflection_count is the number of deflected events; deflection_rate is the fraction."""
    report = compute_usage_roi_report(_USAGE_EVENTS)
    assert report["deflection_count"] == 2  # u2/org-chart + u3/travel-policy
    assert report["deflection_rate"] == round(2 / 8, 4)


# ---------- 7. top_unanswered_topics returns topics sorted by frequency ----------

def test_top_unanswered_topics_sorted_by_frequency():
    """top_unanswered_topics lists topics of unanswered questions, most frequent first."""
    report = compute_usage_roi_report(_USAGE_EVENTS)
    topics = report["top_unanswered_topics"]
    assert isinstance(topics, list)
    # Unanswered: vpn-setup(1), expense-report(1), travel-policy(1) — 3 unanswered events
    assert len(topics) == 3
    # Each entry has topic and count
    for entry in topics:
        assert "topic" in entry
        assert "count" in entry


# ---------- 8. estimated_time_saved_minutes is sum of time_saved_minutes ----------

def test_estimated_time_saved_minutes_is_sum():
    """estimated_time_saved_minutes sums the time_saved_minutes from all events."""
    report = compute_usage_roi_report(_USAGE_EVENTS)
    expected = sum(e["time_saved_minutes"] for e in _USAGE_EVENTS)
    assert report["estimated_time_saved_minutes"] == expected  # 5+10+0+3+0+0+5+8=31


# ---------- 9. empty events produce safe zero defaults ----------

def test_empty_events_return_zero_defaults():
    """An empty event list returns zero for all metrics without errors."""
    report = compute_usage_roi_report([])
    assert report["active_users"] == 0
    assert report["total_questions"] == 0
    assert report["questions_per_division"] == []
    assert report["answer_rate"] == 0.0
    assert report["deflection_count"] == 0
    assert report["deflection_rate"] == 0.0
    assert report["top_unanswered_topics"] == []
    assert report["estimated_time_saved_minutes"] == 0


# ---------- 10. safe output: no raw prompts/answers/secrets in report ----------

def test_report_output_contains_no_raw_content():
    """The report must contain only aggregate metrics and topic strings —
    never raw question text, answers, document text, secrets, or credentials."""
    events_with_sensitive = [
        {"user_id": "u1", "division_id": "d1",
         "question": "What is the WhatsApp revenue share percentage? Bearer token abc123",
         "answered": True, "deflected": False, "topic": "revenue-share",
         "time_saved_minutes": 5},
        {"user_id": "u2", "division_id": "d1",
         "question": "Show me the secret API key for production",
         "answered": False, "deflected": False, "topic": "api-access",
         "time_saved_minutes": 0},
    ]
    report = compute_usage_roi_report(events_with_sensitive)
    serialized = json.dumps(report).lower()

    # NB: "answer" omitted — answer_rate is a legitimate field name.
    for forbidden in ("whatsapp", "revenue share", "bearer", "abc123",
                       "secret", "api key", "production", "password",
                       "credential", "prompt"):
        assert forbidden not in serialized, (
            f"Forbidden term '{forbidden}' found in usage ROI report"
        )


# ---------- 11. unsafe topic labels are redacted ----------

def test_unsafe_unanswered_topic_labels_are_redacted():
    """Unanswered topic labels may come from classifier/user text, so labels containing
    secrets/credentials must be redacted before appearing in the aggregate report."""
    events = [
        {"user_id": "u1", "division_id": "d1",
         "question": "How do I get the production bearer token?",
         "answered": False, "deflected": False,
         "topic": "secret API key production bearer token", "time_saved_minutes": 0},
    ]
    report = compute_usage_roi_report(events)
    serialized = json.dumps(report).lower()

    for forbidden in ("secret", "api key", "production", "bearer", "token"):
        assert forbidden not in serialized, (
            f"Forbidden term '{forbidden}' found in usage ROI topic output"
        )
    assert report["top_unanswered_topics"] == [{"topic": "redacted", "count": 1}]


# ---------- 12. single event produces valid report ----------

def test_single_event_produces_valid_report():
    """A single event yields correct metrics."""
    events = [{"user_id": "u1", "division_id": "d1", "question": "Q?",
               "answered": True, "deflected": False, "topic": "test", "time_saved_minutes": 7}]
    report = compute_usage_roi_report(events)

    assert report["active_users"] == 1
    assert report["total_questions"] == 1
    assert report["answer_rate"] == 1.0
    assert report["deflection_count"] == 0
    assert report["deflection_rate"] == 0.0
    assert report["estimated_time_saved_minutes"] == 7
    assert len(report["questions_per_division"]) == 1
    assert report["questions_per_division"][0]["division_id"] == "d1"
    assert report["questions_per_division"][0]["count"] == 1


# ---------- 12. all unanswered produces 0.0 answer_rate ----------

def test_all_unanswered_produces_zero_answer_rate():
    """When no questions are answered, answer_rate is 0.0."""
    events = [
        {"user_id": "u1", "division_id": "d1", "question": "Q1?",
         "answered": False, "deflected": False, "topic": "t1", "time_saved_minutes": 0},
        {"user_id": "u2", "division_id": "d1", "question": "Q2?",
         "answered": False, "deflected": False, "topic": "t2", "time_saved_minutes": 0},
    ]
    report = compute_usage_roi_report(events)
    assert report["answer_rate"] == 0.0
    assert len(report["top_unanswered_topics"]) == 2


# ---------- 13. missing optional fields default gracefully ----------

def test_missing_optional_fields_default_gracefully():
    """Events with missing optional fields still produce a valid report."""
    events = [
        {"user_id": "u1", "division_id": "d1"},
        {"user_id": "u2"},
    ]
    report = compute_usage_roi_report(events)
    assert report["active_users"] == 2
    assert report["total_questions"] == 2
    # Default: not answered, not deflected, no time saved
    assert report["answer_rate"] == 0.0
    assert report["deflection_count"] == 0
    assert report["estimated_time_saved_minutes"] == 0


# ---------- 14. top_unanswered_topics capped at 10 ----------

def test_top_unanswered_topics_capped_at_ten():
    """top_unanswered_topics returns at most 10 entries."""
    events = [
        {"user_id": "u1", "division_id": "d1", "question": f"Q{i}?",
         "answered": False, "deflected": False, "topic": f"topic-{i}",
         "time_saved_minutes": 0}
        for i in range(15)
    ]
    report = compute_usage_roi_report(events)
    assert len(report["top_unanswered_topics"]) <= 10


# ---------- 15. API route wiring: usage-roi ----------

def test_usage_roi_api_route_is_wired():
    """The POST /api/v1/operate/usage-roi endpoint exists in the FastAPI app."""
    from e2eai.main import app

    openapi = app.openapi()
    assert "/api/v1/operate/usage-roi" in openapi["paths"]


# ---------- 16. questions_per_division entries have required fields ----------

def test_questions_per_division_entries_have_required_fields():
    """Each questions_per_division entry has division_id and count."""
    report = compute_usage_roi_report(_USAGE_EVENTS)
    for entry in report["questions_per_division"]:
        assert "division_id" in entry
        assert "count" in entry
        assert isinstance(entry["count"], int)


# ---------- 17. top_unanswered_topics excludes answered questions ----------

def test_top_unanswered_topics_excludes_answered():
    """Topics from answered questions do not appear in top_unanswered_topics."""
    events = [
        {"user_id": "u1", "division_id": "d1", "question": "Q?",
         "answered": True, "deflected": False, "topic": "answered-topic",
         "time_saved_minutes": 5},
        {"user_id": "u2", "division_id": "d1", "question": "Q2?",
         "answered": False, "deflected": False, "topic": "unanswered-topic",
         "time_saved_minutes": 0},
    ]
    report = compute_usage_roi_report(events)
    topic_names = [t["topic"] for t in report["top_unanswered_topics"]]
    assert "unanswered-topic" in topic_names
    assert "answered-topic" not in topic_names
