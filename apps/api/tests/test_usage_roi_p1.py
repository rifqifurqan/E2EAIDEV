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


# ---------- 18. DB usage/ROI: grouping by user/division ----------

def test_db_usage_roi_groups_by_user_division():
    """aggregate_usage_events_from_db reads persisted user Message rows, joins to
    Conversation->User, and returns safe usage event dicts grouped by user_id/division_id."""
    import asyncio
    import subprocess
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete, func, select

    from e2eai.db import Conversation, Division, Message, User, sessions
    from e2eai.usage_roi import aggregate_usage_events_from_db, compute_usage_roi_report
    from e2eai.seed import seed_demo

    def _migrate():
        subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True, cwd=".")

    async def run():
        async with sessions()() as session:
            await session.execute(delete(Message))
            await session.execute(delete(Conversation))
            await session.commit()

            await seed_demo(session, password="TestUsageROIDB_123456")

            andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
            budi = await session.scalar(select(User).where(func.lower(User.email) == "budi@demo.e2eai"))
            sales_div = await session.scalar(select(Division).where(Division.name == "Sales"))
            hr_div = await session.scalar(select(Division).where(Division.name == "HR"))

            now = datetime.now(timezone.utc)

            andi_conv = Conversation(user_id=andi.id, title="Andi usage conv")
            budi_conv = Conversation(user_id=budi.id, title="Budi usage conv")
            session.add(andi_conv)
            session.add(budi_conv)
            await session.flush()

            # 2 user messages from Andi, 1 from Budi
            session.add(Message(conversation_id=andi_conv.id, role="user",
                                content="q1", tokens=10, latency_ms=None, stop_reason=None))
            session.add(Message(conversation_id=andi_conv.id, role="user",
                                content="q2", tokens=10, latency_ms=None, stop_reason=None))
            session.add(Message(conversation_id=budi_conv.id, role="user",
                                content="q3", tokens=10, latency_ms=None, stop_reason=None))
            # assistant message — must NOT be counted as a question event
            session.add(Message(conversation_id=andi_conv.id, role="assistant",
                                content="a1", tokens=100, latency_ms=200, stop_reason="stop"))
            await session.commit()

            events = await aggregate_usage_events_from_db(
                session,
                window_start=now - timedelta(minutes=1),
                window_end=now + timedelta(minutes=5),
            )

            # 3 user messages → 3 events
            assert len(events) == 3

            for e in events:
                assert "user_id" in e
                assert "division_id" in e
                assert "answered" in e
                assert "deflected" in e
                assert "topic" in e
                assert "time_saved_minutes" in e
                # No raw content fields
                assert "content" not in e
                assert "role" not in e
                assert "model" not in e

            # Verify grouping
            report = compute_usage_roi_report(events)
            assert report["active_users"] >= 2  # andi + budi
            assert report["total_questions"] == 3

            by_div = {d["division_id"]: d["count"] for d in report["questions_per_division"]}
            assert str(sales_div.id) in by_div
            assert str(hr_div.id) in by_div

    _migrate()
    asyncio.run(run())


# ---------- 19. DB usage/ROI: answer/deflection inference from citations ----------

def test_db_usage_roi_answer_inference_from_citations():
    """answered=True when a subsequent assistant Message exists with acceptable stop_reason
    and at least one MessageCitation. deflected=True when citations exist."""
    import asyncio
    import subprocess
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete, func, select

    from e2eai.db import Conversation, Message, MessageCitation, User, sessions
    from e2eai.usage_roi import aggregate_usage_events_from_db
    from e2eai.seed import seed_demo

    def _migrate():
        subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True, cwd=".")

    async def run():
        async with sessions()() as session:
            await session.execute(delete(MessageCitation))
            await session.execute(delete(Message))
            await session.execute(delete(Conversation))
            await session.commit()

            await seed_demo(session, password="TestUsageROIDB_123456")
            andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
            now = datetime.now(timezone.utc)

            conv = Conversation(user_id=andi.id, title="Citation test conv")
            session.add(conv)
            await session.flush()

            # User message → assistant with citation → answered=True, deflected=True
            user_msg1 = Message(conversation_id=conv.id, role="user",
                                content="q cited", tokens=10, latency_ms=None, stop_reason=None)
            session.add(user_msg1)
            await session.flush()
            asst_msg1 = Message(conversation_id=conv.id, role="assistant",
                                content="cited answer", tokens=100, latency_ms=200, stop_reason="stop")
            session.add(asst_msg1)
            await session.flush()
            session.add(MessageCitation(message_id=asst_msg1.id, document_id=None, page=1))
            await session.flush()

            # User message → assistant with error stop_reason → answered=False
            user_msg2 = Message(conversation_id=conv.id, role="user",
                                content="q error", tokens=10, latency_ms=None, stop_reason=None)
            session.add(user_msg2)
            await session.flush()
            session.add(Message(conversation_id=conv.id, role="assistant",
                                content="", tokens=0, latency_ms=100, stop_reason="error"))
            await session.flush()

            # User message → no assistant reply → answered=False
            session.add(Message(conversation_id=conv.id, role="user",
                                content="q unanswered", tokens=10, latency_ms=None, stop_reason=None))
            await session.commit()

            events = await aggregate_usage_events_from_db(
                session,
                window_start=now - timedelta(minutes=1),
                window_end=now + timedelta(minutes=5),
            )

            assert len(events) == 3

            answered_events = [e for e in events if e["answered"]]
            unanswered_events = [e for e in events if not e["answered"]]
            deflected_events = [e for e in events if e["deflected"]]

            assert len(answered_events) == 1, f"Expected 1 answered, got {len(answered_events)}"
            assert len(unanswered_events) == 2, f"Expected 2 unanswered, got {len(unanswered_events)}"
            assert len(deflected_events) >= 1, f"Expected >=1 deflected, got {len(deflected_events)}"

    _migrate()
    asyncio.run(run())


# ---------- 20. DB usage/ROI: deflection from positive feedback ----------

def test_db_usage_roi_deflection_from_positive_feedback():
    """deflected=True when the paired assistant message has positive (up) feedback."""
    import asyncio
    import subprocess
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete, func, select

    from e2eai.db import Conversation, Message, MessageFeedback, User, sessions
    from e2eai.usage_roi import aggregate_usage_events_from_db
    from e2eai.seed import seed_demo

    def _migrate():
        subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True, cwd=".")

    async def run():
        async with sessions()() as session:
            await session.execute(delete(MessageFeedback))
            await session.execute(delete(Message))
            await session.execute(delete(Conversation))
            await session.commit()

            await seed_demo(session, password="TestUsageROIDB_123456")
            andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
            now = datetime.now(timezone.utc)

            conv = Conversation(user_id=andi.id, title="Feedback test conv")
            session.add(conv)
            await session.flush()

            user_msg = Message(conversation_id=conv.id, role="user",
                               content="q feedback", tokens=10, latency_ms=None, stop_reason=None)
            session.add(user_msg)
            await session.flush()
            asst_msg = Message(conversation_id=conv.id, role="assistant",
                               content="answer with feedback", tokens=80, latency_ms=150,
                               stop_reason="stop")
            session.add(asst_msg)
            await session.flush()
            session.add(MessageFeedback(message_id=asst_msg.id, rating="up"))
            await session.commit()

            events = await aggregate_usage_events_from_db(
                session,
                window_start=now - timedelta(minutes=1),
                window_end=now + timedelta(minutes=5),
            )

            assert len(events) == 1
            assert events[0]["deflected"] is True
            assert events[0]["answered"] is True

    _migrate()
    asyncio.run(run())


# ---------- 21. DB usage/ROI: window boundary ----------

def test_db_usage_roi_window_boundary():
    """User messages outside the time window are excluded from usage/ROI aggregation."""
    import asyncio
    import subprocess
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete, func, select, text

    from e2eai.db import Conversation, Message, User, sessions
    from e2eai.usage_roi import aggregate_usage_events_from_db
    from e2eai.seed import seed_demo

    def _migrate():
        subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True, cwd=".")

    async def run():
        async with sessions()() as session:
            await session.execute(delete(Message))
            await session.execute(delete(Conversation))
            await session.commit()

            await seed_demo(session, password="TestUsageROIDB_123456")
            andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))

            now = datetime.now(timezone.utc)
            window_start = now - timedelta(minutes=30)
            window_end = now - timedelta(minutes=10)

            conv = Conversation(user_id=andi.id, title="Window test conv")
            session.add(conv)
            await session.flush()

            # Inside window (backdated)
            msg_in = Message(conversation_id=conv.id, role="user",
                             content="in window", tokens=10, latency_ms=None, stop_reason=None)
            session.add(msg_in)
            await session.flush()
            await session.execute(
                text("UPDATE messages SET created_at = :ts WHERE id = :id"),
                {"ts": window_start + timedelta(minutes=10), "id": str(msg_in.id)},
            )

            # Outside window (created_at = now, after window_end)
            session.add(Message(conversation_id=conv.id, role="user",
                                content="out of window", tokens=10, latency_ms=None, stop_reason=None))
            await session.commit()

            events = await aggregate_usage_events_from_db(session, window_start, window_end)
            assert len(events) == 1, f"Expected 1 in-window event, got {len(events)}"

    _migrate()
    asyncio.run(run())


# ---------- 22. DB usage/ROI: serialization excludes raw content ----------

def test_db_usage_roi_serialization_excludes_raw_content():
    """Usage/ROI events from DB must not contain content, model, role, or any raw text —
    only safe aggregate fields."""
    import asyncio
    import subprocess
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete, func, select

    from e2eai.db import Conversation, Message, User, sessions
    from e2eai.usage_roi import aggregate_usage_events_from_db
    from e2eai.seed import seed_demo

    FORBIDDEN_CONTENT = "WhatsApp revenue share is 30 percent"

    def _migrate():
        subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True, cwd=".")

    async def run():
        async with sessions()() as session:
            await session.execute(delete(Message))
            await session.execute(delete(Conversation))
            await session.commit()

            await seed_demo(session, password="TestUsageROIDB_123456")
            andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
            now = datetime.now(timezone.utc)

            conv = Conversation(user_id=andi.id, title="Safety test conv")
            session.add(conv)
            await session.flush()
            session.add(Message(conversation_id=conv.id, role="user",
                                content=FORBIDDEN_CONTENT, tokens=10, latency_ms=None,
                                stop_reason=None))
            await session.commit()

            events = await aggregate_usage_events_from_db(
                session,
                window_start=now - timedelta(minutes=1),
                window_end=now + timedelta(minutes=5),
            )

            assert len(events) >= 1
            for e in events:
                serialized = json.dumps(e)
                assert FORBIDDEN_CONTENT not in serialized
                for forbidden in ("content", "model", "role", "prompt",
                                  "password", "credential", "bearer", "api_key"):
                    assert forbidden not in serialized.lower(), (
                        f"Forbidden term '{forbidden}' found in usage/ROI event"
                    )

    _migrate()
    asyncio.run(run())


# ---------- 23. DB usage/ROI: unanswered events use safe constant topic ----------

def test_db_usage_roi_unanswered_uses_safe_constant_topic():
    """Unanswered events must use a safe constant topic label, not raw question content."""
    import asyncio
    import subprocess
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete, func, select

    from e2eai.db import Conversation, Message, User, sessions
    from e2eai.usage_roi import aggregate_usage_events_from_db
    from e2eai.seed import seed_demo

    def _migrate():
        subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True, cwd=".")

    async def run():
        async with sessions()() as session:
            await session.execute(delete(Message))
            await session.execute(delete(Conversation))
            await session.commit()

            await seed_demo(session, password="TestUsageROIDB_123456")
            andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
            now = datetime.now(timezone.utc)

            conv = Conversation(user_id=andi.id, title="Topic test conv")
            session.add(conv)
            await session.flush()
            # User question with sensitive text — topic must NOT be raw content
            session.add(Message(conversation_id=conv.id, role="user",
                                content="Show me the secret API key for production",
                                tokens=10, latency_ms=None, stop_reason=None))
            await session.commit()

            events = await aggregate_usage_events_from_db(
                session,
                window_start=now - timedelta(minutes=1),
                window_end=now + timedelta(minutes=5),
            )

            assert len(events) == 1
            topic = events[0]["topic"]
            assert topic == "unanswered", f"Topic must be 'unanswered', got '{topic}'"
            assert "secret" not in topic.lower()
            assert "api key" not in topic.lower()

    _migrate()
    asyncio.run(run())


# ---------- 24. usage-roi-dashboard API route is wired ----------

def test_usage_roi_dashboard_api_route_is_wired():
    """The GET /api/v1/operate/usage-roi-dashboard endpoint exists in the FastAPI app."""
    from e2eai.main import app

    openapi = app.openapi()
    assert "/api/v1/operate/usage-roi-dashboard" in openapi["paths"]


# ---------- 25. usage-roi-dashboard returns safe aggregate report ----------

def test_usage_roi_dashboard_returns_safe_report():
    """get_usage_roi_dashboard returns window metadata, safe usage/ROI report,
    and event count — without leaking any forbidden terms."""
    import asyncio
    import subprocess
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete

    from e2eai.db import Conversation, Message, sessions
    from e2eai.usage_roi import get_usage_roi_dashboard

    # NB: "answer" omitted — answer_rate is a legitimate field name.
    FORBIDDEN = ("prompt", "secret", "password", "credential",
                 "whatsapp", "revenue", "30 percent", "bearer", "api_key",
                 "content", "model")

    def _migrate():
        subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True, cwd=".")

    async def run():
        async with sessions()() as session:
            await session.execute(delete(Message))
            await session.execute(delete(Conversation))
            await session.commit()

            now = datetime.now(timezone.utc)
            window_start = now - timedelta(hours=1)
            window_end = now + timedelta(minutes=1)

            result = await get_usage_roi_dashboard(session, window_start, window_end)

        for key in ("window", "report", "event_count"):
            assert key in result, f"Missing key '{key}' in usage/ROI dashboard result"

        assert "start" in result["window"]
        assert "end" in result["window"]

        for key in ("active_users", "total_questions", "questions_per_division",
                     "answer_rate", "deflection_count", "deflection_rate",
                     "top_unanswered_topics", "estimated_time_saved_minutes"):
            assert key in result["report"], f"Missing key '{key}' in report"

        serialized = json.dumps(result).lower()
        for forbidden in FORBIDDEN:
            assert forbidden not in serialized, (
                f"Forbidden term '{forbidden}' found in usage/ROI dashboard output"
            )

    _migrate()
    asyncio.run(run())
