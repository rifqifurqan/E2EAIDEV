"""P1 SLO metrics and alerting: latency, error rate, cost per conversation, guardrail trigger rate (FR-O5).

SLO metrics are computed from already-recorded chat/message/guardrail/audit-like event inputs.
Outputs are safe: only aggregated metrics and alert metadata — never raw prompts, answers,
document text, restricted titles/snippets, secrets, tokens, or credentials.
"""

import json

from e2eai.slo_metrics import (
    SloPolicy,
    check_slo_alerts,
    compute_slo_metrics,
)


# ---------- Sample event data for tests ----------

_EVENTS = [
    {"latency_ms": 120, "error": False, "cost_usd": 0.003, "guardrail_triggered": False, "tokens": 150},
    {"latency_ms": 200, "error": False, "cost_usd": 0.005, "guardrail_triggered": False, "tokens": 250},
    {"latency_ms": 450, "error": False, "cost_usd": 0.008, "guardrail_triggered": True, "tokens": 400},
    {"latency_ms": 95, "error": True, "cost_usd": 0.001, "guardrail_triggered": False, "tokens": 50},
    {"latency_ms": 310, "error": False, "cost_usd": 0.006, "guardrail_triggered": False, "tokens": 300},
    {"latency_ms": 180, "error": False, "cost_usd": 0.004, "guardrail_triggered": True, "tokens": 200},
    {"latency_ms": 600, "error": True, "cost_usd": 0.002, "guardrail_triggered": False, "tokens": 80},
    {"latency_ms": 140, "error": False, "cost_usd": 0.007, "guardrail_triggered": False, "tokens": 350},
    {"latency_ms": 250, "error": False, "cost_usd": 0.004, "guardrail_triggered": False, "tokens": 220},
    {"latency_ms": 170, "error": False, "cost_usd": 0.005, "guardrail_triggered": True, "tokens": 260},
]

_DEFAULT_POLICY = SloPolicy(
    latency_p50_ms=300,
    latency_p95_ms=800,
    error_rate=0.10,
    cost_per_conversation_usd=0.01,
    guardrail_trigger_rate=0.15,
)


# ---------- 1. compute_slo_metrics returns all four metric families ----------

def test_compute_slo_metrics_returns_latency_error_cost_guardrail():
    """compute_slo_metrics returns all four FR-O5 metric families: latency, error rate,
    cost per conversation, and guardrail trigger rate."""
    metrics = compute_slo_metrics(_EVENTS)

    assert "latency_p50_ms" in metrics
    assert "latency_p95_ms" in metrics
    assert "latency_mean_ms" in metrics
    assert "error_rate" in metrics
    assert "cost_per_conversation_usd" in metrics
    assert "guardrail_trigger_rate" in metrics
    assert "total_events" in metrics
    assert metrics["total_events"] == 10


# ---------- 2. latency percentile computation is correct ----------

def test_latency_percentiles_are_correct():
    """p50 and p95 latency are computed from the sorted latency values."""
    metrics = compute_slo_metrics(_EVENTS)

    # Sorted latencies: 95, 120, 140, 170, 180, 200, 250, 310, 450, 600
    # p50: rank=(50/100)*9=4.5 → lerp(180, 200, 0.5) = 190.0
    # p95: rank=(95/100)*9=8.55 → lerp(450, 600, 0.55) = 532.5
    assert metrics["latency_p50_ms"] == 190.0
    assert metrics["latency_p95_ms"] == 532.5
    assert metrics["latency_mean_ms"] == 251.5  # sum=2515, /10=251.5


# ---------- 3. error rate computation ----------

def test_error_rate_computation():
    """Error rate is the fraction of events where error=True."""
    metrics = compute_slo_metrics(_EVENTS)
    # 2 errors out of 10 events = 0.2
    assert metrics["error_rate"] == 0.2


# ---------- 4. cost per conversation ----------

def test_cost_per_conversation():
    """Cost per conversation is average cost_usd across events."""
    metrics = compute_slo_metrics(_EVENTS)
    # Total cost = 0.003+0.005+0.008+0.001+0.006+0.004+0.002+0.007+0.004+0.005 = 0.045
    # Average = 0.045 / 10 = 0.0045
    assert metrics["cost_per_conversation_usd"] == 0.0045


# ---------- 5. guardrail trigger rate ----------

def test_guardrail_trigger_rate():
    """Guardrail trigger rate is the fraction of events with guardrail_triggered=True."""
    metrics = compute_slo_metrics(_EVENTS)
    # 3 triggers out of 10 = 0.3
    assert metrics["guardrail_trigger_rate"] == 0.3


# ---------- 6. empty events produce safe zero defaults ----------

def test_empty_events_return_zero_metrics():
    """An empty event list returns zero for all metrics without division errors."""
    metrics = compute_slo_metrics([])
    assert metrics["total_events"] == 0
    assert metrics["latency_p50_ms"] == 0.0
    assert metrics["latency_p95_ms"] == 0.0
    assert metrics["latency_mean_ms"] == 0.0
    assert metrics["error_rate"] == 0.0
    assert metrics["cost_per_conversation_usd"] == 0.0
    assert metrics["guardrail_trigger_rate"] == 0.0


# ---------- 7. alert checks: all within SLO ----------

def test_check_slo_alerts_all_within_slo():
    """When all metrics are within thresholds, no alerts fire."""
    metrics = compute_slo_metrics(_EVENTS)
    # Use a lenient policy where everything passes
    lenient = SloPolicy(
        latency_p50_ms=500,
        latency_p95_ms=1000,
        error_rate=0.30,
        cost_per_conversation_usd=0.05,
        guardrail_trigger_rate=0.50,
    )
    alerts = check_slo_alerts(metrics, lenient)

    assert alerts["any_firing"] is False
    assert len(alerts["alerts"]) == 0
    # Five concrete checks: latency p50, latency p95, error rate, cost, and guardrail rate.
    assert alerts["total_checked"] == 5


# ---------- 8. alert checks: latency breaches ----------

def test_check_slo_alerts_latency_breach():
    """Alerts fire when latency metrics exceed configured SLO thresholds."""
    metrics = compute_slo_metrics(_EVENTS)
    # p50=190, p95=600 → set tight thresholds to trigger
    tight = SloPolicy(
        latency_p50_ms=100,
        latency_p95_ms=400,
        error_rate=1.0,
        cost_per_conversation_usd=1.0,
        guardrail_trigger_rate=1.0,
    )
    alerts = check_slo_alerts(metrics, tight)

    assert alerts["any_firing"] is True
    firing_names = {a["name"] for a in alerts["alerts"]}
    assert "latency_p50" in firing_names
    assert "latency_p95" in firing_names

    for alert in alerts["alerts"]:
        if alert["name"] == "latency_p50":
            assert alert["actual"] == 190.0
            assert alert["threshold"] == 100
        if alert["name"] == "latency_p95":
            assert alert["actual"] == 532.5
            assert alert["threshold"] == 400


# ---------- 9. alert checks: error rate breach ----------

def test_check_slo_alerts_error_rate_breach():
    """Alert fires when error rate exceeds the SLO threshold."""
    metrics = compute_slo_metrics(_EVENTS)
    tight = SloPolicy(
        latency_p50_ms=1000,
        latency_p95_ms=2000,
        error_rate=0.10,  # actual is 0.2 → breach
        cost_per_conversation_usd=1.0,
        guardrail_trigger_rate=1.0,
    )
    alerts = check_slo_alerts(metrics, tight)

    assert alerts["any_firing"] is True
    error_alerts = [a for a in alerts["alerts"] if a["name"] == "error_rate"]
    assert len(error_alerts) == 1
    assert error_alerts[0]["actual"] == 0.2
    assert error_alerts[0]["threshold"] == 0.10


# ---------- 10. alert checks: cost per conversation breach ----------

def test_check_slo_alerts_cost_breach():
    """Alert fires when cost per conversation exceeds the SLO threshold."""
    metrics = compute_slo_metrics(_EVENTS)
    tight = SloPolicy(
        latency_p50_ms=1000,
        latency_p95_ms=2000,
        error_rate=1.0,
        cost_per_conversation_usd=0.003,  # actual is 0.0045 → breach
        guardrail_trigger_rate=1.0,
    )
    alerts = check_slo_alerts(metrics, tight)

    assert alerts["any_firing"] is True
    cost_alerts = [a for a in alerts["alerts"] if a["name"] == "cost_per_conversation"]
    assert len(cost_alerts) == 1
    assert cost_alerts[0]["actual"] == 0.0045


# ---------- 11. alert checks: guardrail trigger rate breach ----------

def test_check_slo_alerts_guardrail_breach():
    """Alert fires when guardrail trigger rate exceeds the SLO threshold."""
    metrics = compute_slo_metrics(_EVENTS)
    tight = SloPolicy(
        latency_p50_ms=1000,
        latency_p95_ms=2000,
        error_rate=1.0,
        cost_per_conversation_usd=1.0,
        guardrail_trigger_rate=0.20,  # actual is 0.3 → breach
    )
    alerts = check_slo_alerts(metrics, tight)

    assert alerts["any_firing"] is True
    gr_alerts = [a for a in alerts["alerts"] if a["name"] == "guardrail_trigger_rate"]
    assert len(gr_alerts) == 1
    assert gr_alerts[0]["actual"] == 0.3


# ---------- 12. all four alert types fire simultaneously ----------

def test_check_slo_alerts_all_four_fire():
    """When all four thresholds are breached, all four alert types fire."""
    metrics = compute_slo_metrics(_EVENTS)
    strict = SloPolicy(
        latency_p50_ms=100,
        latency_p95_ms=400,
        error_rate=0.05,
        cost_per_conversation_usd=0.002,
        guardrail_trigger_rate=0.10,
    )
    alerts = check_slo_alerts(metrics, strict)

    assert alerts["any_firing"] is True
    firing_names = {a["name"] for a in alerts["alerts"]}
    assert firing_names == {"latency_p50", "latency_p95", "error_rate", "cost_per_conversation", "guardrail_trigger_rate"}


# ---------- 13. output safety: no raw content leaks ----------

def test_slo_metrics_output_contains_no_raw_content():
    """Metrics and alerts output must contain only numeric/boolean/string metadata —
    never raw prompts, answers, document text, secrets, or credentials."""
    metrics = compute_slo_metrics(_EVENTS)
    alerts = check_slo_alerts(metrics, _DEFAULT_POLICY)

    serialized = json.dumps({"metrics": metrics, "alerts": alerts}).lower()
    for forbidden in ("prompt", "answer", "secret", "password", "token", "credential",
                       "whatsapp", "revenue", "30 percent", "api_key", "bearer"):
        assert forbidden not in serialized, f"Forbidden term '{forbidden}' found in SLO output"


# ---------- 14. single event edge case ----------

def test_single_event_metrics():
    """A single event produces correct metrics (p50=p95=the value)."""
    events = [{"latency_ms": 300, "error": True, "cost_usd": 0.01, "guardrail_triggered": True, "tokens": 100}]
    metrics = compute_slo_metrics(events)

    assert metrics["total_events"] == 1
    assert metrics["latency_p50_ms"] == 300.0
    assert metrics["latency_p95_ms"] == 300.0
    assert metrics["latency_mean_ms"] == 300.0
    assert metrics["error_rate"] == 1.0
    assert metrics["cost_per_conversation_usd"] == 0.01
    assert metrics["guardrail_trigger_rate"] == 1.0


# ---------- 15. SloPolicy defaults ----------

def test_slo_policy_defaults():
    """SloPolicy has reasonable defaults so callers can override only what they need."""
    policy = SloPolicy()
    assert policy.latency_p50_ms > 0
    assert policy.latency_p95_ms > 0
    assert 0 < policy.error_rate <= 1.0
    assert policy.cost_per_conversation_usd > 0
    assert 0 < policy.guardrail_trigger_rate <= 1.0


# ---------- 16. API route wiring smoke test ----------

def test_slo_metrics_api_route_is_wired():
    """The /api/v1/operate/slo-metrics endpoint exists in the FastAPI app."""
    from e2eai.main import app

    openapi = app.openapi()
    assert "/api/v1/operate/slo-metrics" in openapi["paths"]


# ---------- 17. DB window aggregation: safe event dicts from messages ----------

def test_db_slo_window_aggregation_returns_safe_event_dicts():
    """aggregate_slo_events_from_db reads assistant Message rows and returns event dicts
    with numeric/boolean fields only — never message content, role, model, or credentials."""
    import asyncio
    import subprocess
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete, func, select

    from e2eai.db import Conversation, Message, User, sessions
    from e2eai.seed import seed_demo
    from e2eai.slo_metrics import aggregate_slo_events_from_db

    def _migrate():
        subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)

    async def run():
        async with sessions()() as session:
            await session.execute(delete(Message))
            await session.execute(delete(Conversation))
            await session.commit()

            await seed_demo(session, password="TestPassword_123456789")
            user = await session.scalar(
                select(User).where(func.lower(User.email) == "andi@demo.e2eai")
            )

            now = datetime.now(timezone.utc)

            # Seed a conversation + assistant message inside the window
            conv = Conversation(user_id=user.id, title="SLO test conv")
            session.add(conv)
            await session.flush()

            msg = Message(
                conversation_id=conv.id,
                role="assistant",
                content="WhatsApp revenue share is 30 percent",  # must NOT appear in events
                model="test-model",
                tokens=150,
                latency_ms=300,
                stop_reason="stop",
            )
            session.add(msg)
            # Also add a user message (should be excluded from aggregation)
            user_msg = Message(
                conversation_id=conv.id,
                role="user",
                content="What is the revenue share?",  # must NOT appear
                model=None,
                tokens=None,
                latency_ms=None,
                stop_reason=None,
            )
            session.add(user_msg)
            await session.commit()

            events = await aggregate_slo_events_from_db(
                session,
                window_start=now - timedelta(minutes=5),
                window_end=now + timedelta(minutes=5),
            )

            # Must have at least one event (the assistant message)
            assert len(events) >= 1

            for e in events:
                # Shape: only expected safe keys present
                assert "latency_ms" in e
                assert "error" in e
                assert "cost_usd" in e
                assert "guardrail_triggered" in e
                # Raw content / sensitive fields must be absent
                assert "content" not in e
                assert "role" not in e
                assert "model" not in e
                serialized = json.dumps(e)
                assert "WhatsApp" not in serialized
                assert "revenue share" not in serialized
                assert "30 percent" not in serialized
                assert "What is the revenue" not in serialized

            # Verify the numeric values for the assistant message
            matching = [e for e in events if e["latency_ms"] == 300]
            assert len(matching) == 1
            assert matching[0]["error"] is False
            assert matching[0]["cost_usd"] > 0

    _migrate()
    asyncio.run(run())


# ---------- 18. DB window aggregation: time window boundary ----------

def test_db_slo_window_aggregation_respects_time_window():
    """Messages with created_at outside the window are excluded from aggregation."""
    import asyncio
    import subprocess
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete, func, select, text

    from e2eai.db import Conversation, Message, User, sessions
    from e2eai.seed import seed_demo
    from e2eai.slo_metrics import aggregate_slo_events_from_db

    def _migrate():
        subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)

    async def run():
        async with sessions()() as session:
            await session.execute(delete(Message))
            await session.execute(delete(Conversation))
            await session.commit()

            await seed_demo(session, password="TestPassword_123456789")
            user = await session.scalar(
                select(User).where(func.lower(User.email) == "andi@demo.e2eai")
            )

            now = datetime.now(timezone.utc)
            window_start = now - timedelta(minutes=30)
            window_end = now - timedelta(minutes=10)  # in the past

            conv = Conversation(user_id=user.id, title="SLO window test conv")
            session.add(conv)
            await session.flush()

            # Message INSIDE window: backdate via INSERT with explicit created_at
            msg_in = Message(
                conversation_id=conv.id,
                role="assistant",
                content="Inside window content",
                model="test-model",
                tokens=50,
                latency_ms=100,
                stop_reason="stop",
            )
            session.add(msg_in)
            await session.flush()
            # Force created_at into the window
            await session.execute(
                text("UPDATE messages SET created_at = :ts WHERE id = :id"),
                {"ts": window_start + timedelta(minutes=10), "id": str(msg_in.id)},
            )

            # Message OUTSIDE window: created_at = now (after window_end)
            msg_out = Message(
                conversation_id=conv.id,
                role="assistant",
                content="Outside window content",
                model="test-model",
                tokens=200,
                latency_ms=999,
                stop_reason="stop",
            )
            session.add(msg_out)
            await session.commit()

            events = await aggregate_slo_events_from_db(session, window_start, window_end)

            # Only msg_in should be in events (latency_ms=100, not latency_ms=999)
            latencies = [e["latency_ms"] for e in events]
            assert 100 in latencies, "In-window message must be included"
            assert 999 not in latencies, "Out-of-window message must be excluded"

    _migrate()
    asyncio.run(run())


# ---------- 19. Alert persistence: stores safe fields only ----------

def test_slo_alert_persistence_stores_safe_fields_only():
    """persist_slo_alerts writes SloAlert rows containing only alert_name, actual,
    threshold, window_start, window_end, created_by — never message content or secrets."""
    import asyncio
    import subprocess
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete, select

    from e2eai.db import sessions
    from e2eai.slo_metrics import SloAlert, persist_slo_alerts

    def _migrate():
        subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)

    async def run():
        async with sessions()() as session:
            await session.execute(delete(SloAlert))
            await session.commit()

            now = datetime.now(timezone.utc)
            window_start = now - timedelta(hours=1)
            window_end = now

            fired_alerts = {
                "any_firing": True,
                "total_checked": 5,
                "alerts": [
                    {"name": "error_rate", "actual": 0.25, "threshold": 0.10},
                    {"name": "latency_p95", "actual": 1800.0, "threshold": 1000.0},
                ],
            }

            ids = await persist_slo_alerts(
                session,
                fired_alerts,
                window_start=window_start,
                window_end=window_end,
                created_by="test_actor",
            )

            assert len(ids) == 2

            rows = (await session.execute(select(SloAlert))).scalars().all()
            persisted = [r for r in rows]
            assert len(persisted) >= 2

            names = {r.alert_name for r in persisted}
            assert "error_rate" in names
            assert "latency_p95" in names

            for row in persisted:
                # Only safe numeric/string fields should exist on the model
                assert hasattr(row, "alert_name")
                assert hasattr(row, "actual")
                assert hasattr(row, "threshold")
                assert hasattr(row, "window_start")
                assert hasattr(row, "window_end")
                assert hasattr(row, "created_by")
                # Values must be numeric/string, not blobs of message text
                assert isinstance(row.actual, float)
                assert isinstance(row.threshold, float)
                assert row.created_by == "test_actor"

    _migrate()
    asyncio.run(run())


# ---------- 20. Leakage guard: raw message content absent from persisted alerts ----------

def test_slo_alert_persistence_leakage_guard_raw_content_absent():
    """Raw message content ('WhatsApp revenue share is 30 percent') must not appear
    in persisted SloAlert rows or in the slo-window endpoint output."""
    import asyncio
    import subprocess
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete, func, select

    from e2eai.db import Conversation, Message, User, sessions
    from e2eai.seed import seed_demo
    from e2eai.slo_metrics import (
        SloAlert,
        SloPolicy,
        aggregate_slo_events_from_db,
        check_slo_alerts,
        compute_slo_metrics,
        persist_slo_alerts,
    )

    FORBIDDEN = "WhatsApp revenue share is 30 percent"

    def _migrate():
        subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)

    async def run():
        async with sessions()() as session:
            await session.execute(delete(SloAlert))
            await session.execute(delete(Message))
            await session.execute(delete(Conversation))
            await session.commit()

            await seed_demo(session, password="TestPassword_123456789")
            user = await session.scalar(
                select(User).where(func.lower(User.email) == "andi@demo.e2eai")
            )

            now = datetime.now(timezone.utc)

            conv = Conversation(user_id=user.id, title="Leakage guard conv")
            session.add(conv)
            await session.flush()

            # Message containing sensitive content that must NOT leak into alerts
            session.add(Message(
                conversation_id=conv.id,
                role="assistant",
                content=FORBIDDEN,
                model="test-model",
                tokens=10,
                latency_ms=5000,  # very high latency → will trigger alert
                stop_reason="stop",
            ))
            await session.commit()

            events = await aggregate_slo_events_from_db(
                session,
                window_start=now - timedelta(minutes=5),
                window_end=now + timedelta(minutes=5),
            )

            # Events must not contain forbidden content
            for e in events:
                assert FORBIDDEN not in json.dumps(e)

            metrics = compute_slo_metrics(events)
            tight_policy = SloPolicy(latency_p50_ms=10, latency_p95_ms=20, error_rate=1.0,
                                     cost_per_conversation_usd=1.0, guardrail_trigger_rate=1.0)
            alerts = check_slo_alerts(metrics, tight_policy)
            assert alerts["any_firing"] is True

            ids = await persist_slo_alerts(
                session, alerts,
                window_start=now - timedelta(minutes=5),
                window_end=now + timedelta(minutes=5),
                created_by="leakage_guard_test",
            )
            assert len(ids) > 0

            rows = (await session.execute(select(SloAlert))).scalars().all()
            for row in rows:
                row_str = json.dumps({
                    "alert_name": row.alert_name,
                    "actual": row.actual,
                    "threshold": row.threshold,
                    "created_by": row.created_by,
                })
                assert FORBIDDEN not in row_str, (
                    f"Forbidden content found in persisted alert: {row_str!r}"
                )

    _migrate()
    asyncio.run(run())


# ---------- 21. slo-window API endpoint wiring smoke ----------

def test_slo_window_api_route_is_wired():
    """The /api/v1/operate/slo-window endpoint exists in the FastAPI app."""
    from e2eai.main import app

    openapi = app.openapi()
    assert "/api/v1/operate/slo-window" in openapi["paths"]


# ---------- 22. DB window aggregation includes guardrail audit entries (FR-O5) ----------

def test_aggregate_slo_events_includes_guardrail_audit_entries():
    """aggregate_slo_events_from_db reads retrieval.context.blocked AuditEntry rows inside
    the time window and returns events with guardrail_triggered=True, making
    guardrail_trigger_rate > 0. AuditEntry details must NOT appear in event dicts."""
    import asyncio
    import subprocess
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete

    from e2eai.audit import record as audit_record
    from e2eai.db import AuditEntry, sessions
    from e2eai.slo_metrics import aggregate_slo_events_from_db, compute_slo_metrics

    def _migrate():
        subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)

    async def run():
        async with sessions()() as session:
            # Isolate: clear audit_log so no prior entries interfere
            await session.execute(delete(AuditEntry))
            await session.commit()

            # Record a guardrail-block audit entry (at = now, inside the upcoming window)
            now = datetime.now(timezone.utc)
            await audit_record(
                session,
                actor="user:andi",
                action="retrieval.context.blocked",
                target="doc:abc",
                details={"reason": "no_permission", "raw_content": "Confidential Budget Q4"},
            )
            await session.commit()

            events = await aggregate_slo_events_from_db(
                session,
                window_start=now - timedelta(minutes=1),
                window_end=now + timedelta(minutes=5),
            )

        guardrail_events = [e for e in events if e.get("guardrail_triggered")]
        assert len(guardrail_events) >= 1, (
            "Expected at least one guardrail event from retrieval.context.blocked AuditEntry"
        )

        metrics = compute_slo_metrics(events)
        assert metrics["guardrail_trigger_rate"] > 0, (
            f"guardrail_trigger_rate must be > 0, got {metrics['guardrail_trigger_rate']}"
        )

        # Each guardrail event must carry only safe synthetic values — no detail bleed
        for e in guardrail_events:
            assert e["latency_ms"] == 0
            assert e["error"] is False
            assert e["cost_usd"] == 0.0
            assert e["guardrail_triggered"] is True
            serialized = json.dumps(e)
            assert "Confidential Budget Q4" not in serialized, (
                "AuditEntry detail raw_content must not appear in event"
            )
            assert "raw_content" not in serialized, (
                "AuditEntry detail keys must not appear in event"
            )

    _migrate()
    asyncio.run(run())


# ---------- 23. DB window aggregation excludes out-of-window audit entries ----------

def test_aggregate_slo_events_excludes_out_of_window_audit_entries():
    """retrieval.context.blocked AuditEntry rows with at before window_start must not
    appear in aggregate_slo_events_from_db results."""
    import asyncio
    import subprocess
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete

    from e2eai.audit import record as audit_record
    from e2eai.db import AuditEntry, sessions
    from e2eai.slo_metrics import aggregate_slo_events_from_db

    def _migrate():
        subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)

    async def run():
        async with sessions()() as session:
            await session.execute(delete(AuditEntry))
            await session.commit()

            # Insert entry now; query a future window so the entry is before window_start
            await audit_record(
                session,
                actor="user:budi",
                action="retrieval.context.blocked",
                target="doc:xyz",
                details={"reason": "expired_share"},
            )
            await session.commit()

            now = datetime.now(timezone.utc)
            # Window starts 1 minute in the future — entry (at ≤ now) is excluded
            events = await aggregate_slo_events_from_db(
                session,
                window_start=now + timedelta(minutes=1),
                window_end=now + timedelta(minutes=5),
            )

        assert all(not e.get("guardrail_triggered") for e in events), (
            "Out-of-window retrieval.context.blocked entry must not produce a guardrail event"
        )

    _migrate()
    asyncio.run(run())


# ---------- 24. SLO alert notifications delivered to admin/evaluator only ----------

def test_slo_alert_notifications_delivered_to_admin_evaluator_only():
    """When SLO alerts fire, safe in-app notifications are delivered to admin and evaluator
    users. Business users get no notification. Details contain only alert metadata —
    never raw prompts, answers, document text, secrets, tokens, or credentials."""
    import asyncio
    import subprocess
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete, func, select

    from e2eai.auth import hash_password
    from e2eai.db import (
        LocalCredential,
        Notification,
        Organization,
        Role,
        User,
        UserRole,
        sessions,
    )
    from e2eai.seed import seed_roles
    from e2eai.slo_metrics import notify_slo_alerts

    FORBIDDEN = ("prompt", "answer", "secret", "password", "token", "credential",
                 "whatsapp", "revenue", "30 percent", "bearer")

    def _migrate():
        subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)

    async def run():
        async with sessions()() as session:
            await session.execute(delete(Notification))
            await session.commit()

            await seed_roles(session)
            org = await session.scalar(select(Organization).where(Organization.name == "System"))
            if org is None:
                org = Organization(name="System", created_by="test")
                session.add(org)
                await session.flush()

            roles = {r.name: r for r in await session.scalars(select(Role))}
            pw_hash = hash_password("TestNotif_123456789")

            admin_user = await session.scalar(select(User).where(func.lower(User.email) == "admin_slo@test.local"))
            if admin_user is None:
                admin_user = User(org_id=org.id, email="admin_slo@test.local", display_name="Admin SLO", created_by="test")
                session.add(admin_user)
                await session.flush()
                session.add(LocalCredential(user_id=admin_user.id, password_hash=pw_hash))
                session.add(UserRole(user_id=admin_user.id, role_id=roles["admin"].id))

            eval_user = await session.scalar(select(User).where(func.lower(User.email) == "evaluator_slo@test.local"))
            if eval_user is None:
                eval_user = User(org_id=org.id, email="evaluator_slo@test.local", display_name="Evaluator SLO", created_by="test")
                session.add(eval_user)
                await session.flush()
                session.add(LocalCredential(user_id=eval_user.id, password_hash=pw_hash))
                session.add(UserRole(user_id=eval_user.id, role_id=roles["evaluator"].id))

            biz_user = await session.scalar(select(User).where(func.lower(User.email) == "biz_slo@test.local"))
            if biz_user is None:
                biz_user = User(org_id=org.id, email="biz_slo@test.local", display_name="Biz SLO", created_by="test")
                session.add(biz_user)
                await session.flush()
                session.add(LocalCredential(user_id=biz_user.id, password_hash=pw_hash))
                session.add(UserRole(user_id=biz_user.id, role_id=roles["business_user"].id))
            await session.commit()

            now = datetime.now(timezone.utc)
            window_start = now - timedelta(hours=1)
            window_end = now

            fired_alerts = {
                "any_firing": True,
                "total_checked": 5,
                "alerts": [
                    {"name": "error_rate", "actual": 0.25, "threshold": 0.10},
                    {"name": "latency_p95", "actual": 1800.0, "threshold": 1000.0},
                ],
            }

            count = await notify_slo_alerts(session, fired_alerts, window_start, window_end)
            await session.commit()

            # At least 2 alerts × 2 recipients (admin + evaluator); may be more if other
            # admin/evaluator users exist in the DB from prior test setup.
            assert count >= 4, f"Expected at least 4 notifications, got {count}"
            assert count % len(fired_alerts["alerts"]) == 0, "Count must be a multiple of fired alert count"

            admin_notifs = (await session.execute(
                select(Notification).where(Notification.user_id == admin_user.id)
            )).scalars().all()
            assert len(admin_notifs) == 2

            eval_notifs = (await session.execute(
                select(Notification).where(Notification.user_id == eval_user.id)
            )).scalars().all()
            assert len(eval_notifs) == 2

            # Business user must get no notifications
            biz_notifs = (await session.execute(
                select(Notification).where(Notification.user_id == biz_user.id)
            )).scalars().all()
            assert len(biz_notifs) == 0

            for notif in admin_notifs + eval_notifs:
                assert notif.kind == "slo.alert.fired"
                assert "alert_name" in notif.details
                assert "actual" in notif.details
                assert "threshold" in notif.details
                serialized = json.dumps(notif.details).lower()
                for forbidden in FORBIDDEN:
                    assert forbidden not in serialized, (
                        f"Forbidden term '{forbidden}' in SLO notification details"
                    )

    _migrate()
    asyncio.run(run())
