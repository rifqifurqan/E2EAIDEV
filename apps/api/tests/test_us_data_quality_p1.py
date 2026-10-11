from datetime import UTC, datetime, timedelta

from e2eai.data_quality import find_duplicate_titles, is_stale_document, is_unparseable


def test_find_duplicate_titles_groups_case_and_whitespace_duplicates() -> None:
    docs = [
        {"title": "Revenue Policy"},
        {"title": "  revenue policy  "},
        {"title": "HR Handbook"},
        {"title": "Security Standard"},
    ]

    assert find_duplicate_titles(docs) == [[0, 1]]


def test_find_duplicate_titles_groups_near_duplicates_by_normalized_tokens() -> None:
    docs = [
        {"title": "Q4 WhatsApp partnership revenue-share memo"},
        {"title": "WhatsApp Partnership Revenue Share Memo Q4"},
        {"title": "Employee leave policy"},
    ]

    assert find_duplicate_titles(docs) == [[0, 1]]


def test_find_duplicate_titles_ignores_singletons_and_blank_titles() -> None:
    docs = [
        {"title": ""},
        {"title": "   "},
        {"title": "Unique One"},
        {"title": "Unique Two"},
    ]

    assert find_duplicate_titles(docs) == []


def test_is_stale_document_uses_age_threshold_in_days() -> None:
    now = datetime(2026, 10, 11, tzinfo=UTC)

    assert is_stale_document(now - timedelta(days=91), now=now, max_age_days=90) is True
    assert is_stale_document(now - timedelta(days=90), now=now, max_age_days=90) is False


def test_is_stale_document_treats_missing_mtime_as_stale() -> None:
    now = datetime(2026, 10, 11, tzinfo=UTC)

    assert is_stale_document(None, now=now, max_age_days=90) is True


def test_is_unparseable_flags_status_or_parse_error() -> None:
    assert is_unparseable("unparseable") is True
    assert is_unparseable("failed") is True
    assert is_unparseable("active", parse_error="OCR failed") is True
    assert is_unparseable("active", parse_error="") is False
