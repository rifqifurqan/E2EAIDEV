"""P1 FinOps: spend per user/team/division/bot, budgets, alerts, chargeback reports (FR-O6).

Spend aggregation, budget threshold alerts, and chargeback reports use safe metadata only —
never raw prompts, answers, document text, secrets, tokens, or credentials.
"""

import json

from e2eai.finops import (
    BudgetPolicy,
    aggregate_spend,
    check_budget_alerts,
    build_chargeback_report,
)


# ---------- Sample spend event data for tests ----------

_SPEND_EVENTS = [
    {"user_id": "u1", "team_id": "t1", "division_id": "d1", "bot_id": "b1", "cost_usd": 0.010, "tokens": 500},
    {"user_id": "u1", "team_id": "t1", "division_id": "d1", "bot_id": "b1", "cost_usd": 0.015, "tokens": 750},
    {"user_id": "u2", "team_id": "t1", "division_id": "d1", "bot_id": "b2", "cost_usd": 0.008, "tokens": 400},
    {"user_id": "u2", "team_id": "t2", "division_id": "d2", "bot_id": "b1", "cost_usd": 0.020, "tokens": 1000},
    {"user_id": "u3", "team_id": "t2", "division_id": "d2", "bot_id": "b2", "cost_usd": 0.005, "tokens": 250},
    {"user_id": "u3", "team_id": "t2", "division_id": "d2", "bot_id": "b2", "cost_usd": 0.012, "tokens": 600},
    {"user_id": "u1", "team_id": "t1", "division_id": "d1", "bot_id": "b2", "cost_usd": 0.007, "tokens": 350},
]


# ---------- 1. aggregate_spend returns spend by all four dimensions ----------

def test_aggregate_spend_returns_all_four_dimensions():
    """aggregate_spend returns spend totals grouped by user, team, division, and bot."""
    result = aggregate_spend(_SPEND_EVENTS)

    assert "by_user" in result
    assert "by_team" in result
    assert "by_division" in result
    assert "by_bot" in result
    assert "total_cost_usd" in result
    assert "total_events" in result
    assert result["total_events"] == 7


# ---------- 2. spend aggregation by user is correct ----------

def test_spend_by_user_is_correct():
    """Spend per user sums cost_usd correctly."""
    result = aggregate_spend(_SPEND_EVENTS)

    by_user = {e["id"]: e["cost_usd"] for e in result["by_user"]}
    # u1: 0.010 + 0.015 + 0.007 = 0.032
    assert round(by_user["u1"], 6) == 0.032
    # u2: 0.008 + 0.020 = 0.028
    assert round(by_user["u2"], 6) == 0.028
    # u3: 0.005 + 0.012 = 0.017
    assert round(by_user["u3"], 6) == 0.017


# ---------- 3. spend aggregation by team ----------

def test_spend_by_team_is_correct():
    """Spend per team sums cost_usd correctly."""
    result = aggregate_spend(_SPEND_EVENTS)

    by_team = {e["id"]: e["cost_usd"] for e in result["by_team"]}
    # t1: 0.010 + 0.015 + 0.008 + 0.007 = 0.040
    assert round(by_team["t1"], 6) == 0.04
    # t2: 0.020 + 0.005 + 0.012 = 0.037
    assert round(by_team["t2"], 6) == 0.037


# ---------- 4. spend aggregation by division ----------

def test_spend_by_division_is_correct():
    """Spend per division sums cost_usd correctly."""
    result = aggregate_spend(_SPEND_EVENTS)

    by_div = {e["id"]: e["cost_usd"] for e in result["by_division"]}
    # d1: 0.010 + 0.015 + 0.008 + 0.007 = 0.040
    assert round(by_div["d1"], 6) == 0.04
    # d2: 0.020 + 0.005 + 0.012 = 0.037
    assert round(by_div["d2"], 6) == 0.037


# ---------- 5. spend aggregation by bot ----------

def test_spend_by_bot_is_correct():
    """Spend per bot sums cost_usd correctly."""
    result = aggregate_spend(_SPEND_EVENTS)

    by_bot = {e["id"]: e["cost_usd"] for e in result["by_bot"]}
    # b1: 0.010 + 0.015 + 0.020 = 0.045
    assert round(by_bot["b1"], 6) == 0.045
    # b2: 0.008 + 0.005 + 0.012 + 0.007 = 0.032
    assert round(by_bot["b2"], 6) == 0.032


# ---------- 6. total cost is sum of all events ----------

def test_total_cost_is_sum_of_all_events():
    """total_cost_usd is the sum of all event cost_usd values."""
    result = aggregate_spend(_SPEND_EVENTS)
    expected = sum(e["cost_usd"] for e in _SPEND_EVENTS)
    assert round(result["total_cost_usd"], 6) == round(expected, 6)


# ---------- 7. empty events produce safe zero defaults ----------

def test_empty_events_return_zero_spend():
    """An empty event list returns zero for all spend aggregations without errors."""
    result = aggregate_spend([])
    assert result["total_events"] == 0
    assert result["total_cost_usd"] == 0.0
    assert result["by_user"] == []
    assert result["by_team"] == []
    assert result["by_division"] == []
    assert result["by_bot"] == []


# ---------- 8. budget alerts: all within budget ----------

def test_budget_alerts_all_within_budget():
    """When all dimension spends are within budget, no alerts fire."""
    spend = aggregate_spend(_SPEND_EVENTS)
    lenient = BudgetPolicy(
        user_budget_usd=1.0,
        team_budget_usd=1.0,
        division_budget_usd=1.0,
        bot_budget_usd=1.0,
    )
    alerts = check_budget_alerts(spend, lenient)

    assert alerts["any_firing"] is False
    assert len(alerts["alerts"]) == 0
    assert alerts["total_checked"] > 0


# ---------- 9. budget alerts: user budget breach ----------

def test_budget_alerts_user_budget_breach():
    """Alert fires when a user's spend exceeds the budget threshold."""
    spend = aggregate_spend(_SPEND_EVENTS)
    # u1 spend = 0.032 → set threshold at 0.03 to trigger
    tight = BudgetPolicy(
        user_budget_usd=0.03,
        team_budget_usd=1.0,
        division_budget_usd=1.0,
        bot_budget_usd=1.0,
    )
    alerts = check_budget_alerts(spend, tight)

    assert alerts["any_firing"] is True
    user_alerts = [a for a in alerts["alerts"] if a["dimension"] == "user"]
    assert len(user_alerts) >= 1
    breaching_ids = {a["id"] for a in user_alerts}
    assert "u1" in breaching_ids


# ---------- 10. budget alerts: team budget breach ----------

def test_budget_alerts_team_budget_breach():
    """Alert fires when a team's spend exceeds the budget threshold."""
    spend = aggregate_spend(_SPEND_EVENTS)
    # t1 spend = 0.040 → set threshold at 0.035
    tight = BudgetPolicy(
        user_budget_usd=1.0,
        team_budget_usd=0.035,
        division_budget_usd=1.0,
        bot_budget_usd=1.0,
    )
    alerts = check_budget_alerts(spend, tight)

    assert alerts["any_firing"] is True
    team_alerts = [a for a in alerts["alerts"] if a["dimension"] == "team"]
    assert len(team_alerts) >= 1
    breaching_ids = {a["id"] for a in team_alerts}
    assert "t1" in breaching_ids


# ---------- 11. budget alerts: division budget breach ----------

def test_budget_alerts_division_budget_breach():
    """Alert fires when a division's spend exceeds the budget threshold."""
    spend = aggregate_spend(_SPEND_EVENTS)
    # d1 spend = 0.040 → set threshold at 0.035
    tight = BudgetPolicy(
        user_budget_usd=1.0,
        team_budget_usd=1.0,
        division_budget_usd=0.035,
        bot_budget_usd=1.0,
    )
    alerts = check_budget_alerts(spend, tight)

    assert alerts["any_firing"] is True
    div_alerts = [a for a in alerts["alerts"] if a["dimension"] == "division"]
    assert len(div_alerts) >= 1
    breaching_ids = {a["id"] for a in div_alerts}
    assert "d1" in breaching_ids


# ---------- 12. budget alerts: bot budget breach ----------

def test_budget_alerts_bot_budget_breach():
    """Alert fires when a bot's spend exceeds the budget threshold."""
    spend = aggregate_spend(_SPEND_EVENTS)
    # b1 spend = 0.045 → set threshold at 0.04
    tight = BudgetPolicy(
        user_budget_usd=1.0,
        team_budget_usd=1.0,
        division_budget_usd=1.0,
        bot_budget_usd=0.04,
    )
    alerts = check_budget_alerts(spend, tight)

    assert alerts["any_firing"] is True
    bot_alerts = [a for a in alerts["alerts"] if a["dimension"] == "bot"]
    assert len(bot_alerts) >= 1
    breaching_ids = {a["id"] for a in bot_alerts}
    assert "b1" in breaching_ids


# ---------- 13. budget alerts: multiple dimensions breach ----------

def test_budget_alerts_multiple_dimensions_breach():
    """When budgets are tight across all dimensions, alerts fire for each breaching entity."""
    spend = aggregate_spend(_SPEND_EVENTS)
    tight = BudgetPolicy(
        user_budget_usd=0.01,
        team_budget_usd=0.01,
        division_budget_usd=0.01,
        bot_budget_usd=0.01,
    )
    alerts = check_budget_alerts(spend, tight)

    assert alerts["any_firing"] is True
    dimensions = {a["dimension"] for a in alerts["alerts"]}
    assert dimensions == {"user", "team", "division", "bot"}


# ---------- 14. chargeback report: safe output ----------

def test_chargeback_report_is_safe_aggregate():
    """build_chargeback_report returns only aggregated spend summaries per dimension —
    never raw prompts, answers, document text, secrets, or credentials."""
    spend = aggregate_spend(_SPEND_EVENTS)
    report = build_chargeback_report(spend)

    assert "by_user" in report
    assert "by_team" in report
    assert "by_division" in report
    assert "by_bot" in report
    assert "total_cost_usd" in report
    assert "generated_at" in report

    serialized = json.dumps(report).lower()
    for forbidden in ("prompt", "answer", "secret", "password", "credential",
                       "bearer", "api_key", "content", "whatsapp", "revenue"):
        assert forbidden not in serialized, f"Forbidden term '{forbidden}' found in chargeback report"


# ---------- 15. chargeback report: each entry has id, cost, event_count ----------

def test_chargeback_report_entries_have_required_fields():
    """Each chargeback report entry has id, cost_usd, and event_count."""
    spend = aggregate_spend(_SPEND_EVENTS)
    report = build_chargeback_report(spend)

    for dimension in ("by_user", "by_team", "by_division", "by_bot"):
        for entry in report[dimension]:
            assert "id" in entry
            assert "cost_usd" in entry
            assert "event_count" in entry
            assert isinstance(entry["cost_usd"], float)
            assert isinstance(entry["event_count"], int)


# ---------- 16. chargeback report: empty spend ----------

def test_chargeback_report_empty_spend():
    """Chargeback report on empty spend has zero totals and empty dimension lists."""
    spend = aggregate_spend([])
    report = build_chargeback_report(spend)

    assert report["total_cost_usd"] == 0.0
    assert report["by_user"] == []
    assert report["by_team"] == []
    assert report["by_division"] == []
    assert report["by_bot"] == []


# ---------- 17. BudgetPolicy defaults ----------

def test_budget_policy_defaults():
    """BudgetPolicy has reasonable defaults so callers can override only what they need."""
    policy = BudgetPolicy()
    assert policy.user_budget_usd > 0
    assert policy.team_budget_usd > 0
    assert policy.division_budget_usd > 0
    assert policy.bot_budget_usd > 0


# ---------- 18. output safety: spend aggregation contains no raw content ----------

def test_spend_aggregation_output_contains_no_raw_content():
    """Spend aggregation and budget alerts output must contain only numeric/string metadata —
    never raw prompts, answers, document text, secrets, or credentials."""
    spend = aggregate_spend(_SPEND_EVENTS)
    policy = BudgetPolicy(user_budget_usd=0.01, team_budget_usd=0.01,
                          division_budget_usd=0.01, bot_budget_usd=0.01)
    alerts = check_budget_alerts(spend, policy)

    serialized = json.dumps({"spend": spend, "alerts": alerts}).lower()
    for forbidden in ("prompt", "answer", "secret", "password", "credential",
                       "bearer", "api_key", "content", "whatsapp", "revenue"):
        assert forbidden not in serialized, f"Forbidden term '{forbidden}' found in FinOps output"


# ---------- 19. API route wiring: finops-spend ----------

def test_finops_spend_api_route_is_wired():
    """The /api/v1/operate/finops-spend endpoint exists in the FastAPI app."""
    from e2eai.main import app

    openapi = app.openapi()
    assert "/api/v1/operate/finops-spend" in openapi["paths"]


# ---------- 20. API route wiring: finops-chargeback ----------

def test_finops_chargeback_api_route_is_wired():
    """The /api/v1/operate/finops-chargeback endpoint exists in the FastAPI app."""
    from e2eai.main import app

    openapi = app.openapi()
    assert "/api/v1/operate/finops-chargeback" in openapi["paths"]


# ---------- 21. single event aggregation ----------

def test_single_event_aggregation():
    """A single event produces correct per-dimension spend."""
    events = [{"user_id": "u1", "team_id": "t1", "division_id": "d1",
               "bot_id": "b1", "cost_usd": 0.05, "tokens": 2500}]
    result = aggregate_spend(events)

    assert result["total_events"] == 1
    assert result["total_cost_usd"] == 0.05
    assert len(result["by_user"]) == 1
    assert result["by_user"][0]["id"] == "u1"
    assert result["by_user"][0]["cost_usd"] == 0.05


# ---------- 22. token counts are aggregated per dimension ----------

def test_token_counts_aggregated_per_dimension():
    """Each dimension entry includes aggregated token counts."""
    result = aggregate_spend(_SPEND_EVENTS)

    for dimension in ("by_user", "by_team", "by_division", "by_bot"):
        for entry in result[dimension]:
            assert "tokens" in entry
            assert isinstance(entry["tokens"], int)

    # Verify u1 total tokens: 500 + 750 + 350 = 1600
    u1_entry = next(e for e in result["by_user"] if e["id"] == "u1")
    assert u1_entry["tokens"] == 1600


# ---------- 23. DB FinOps: spend aggregation groups by user/team/division ----------

def test_db_finops_spend_aggregation_groups_by_user_team_division():
    """aggregate_spend_events_from_db reads persisted assistant Message rows, joins to
    Conversation/User/TeamMember/Team, and returns safe spend event dicts compatible
    with aggregate_spend, grouped by user_id, team_id, division_id, and bot_id."""
    import asyncio
    import subprocess
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete, func, select

    from e2eai.db import (
        Conversation, Division, Message, Team, TeamMember, User, sessions,
    )
    from e2eai.finops import aggregate_spend, aggregate_spend_events_from_db
    from e2eai.seed import seed_demo

    def _migrate():
        subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True, cwd=".")

    async def run():
        async with sessions()() as session:
            await session.execute(delete(Message))
            await session.execute(delete(Conversation))
            await session.commit()

            await seed_demo(session, password="TestFinOpsDB_1234567")

            andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
            budi = await session.scalar(select(User).where(func.lower(User.email) == "budi@demo.e2eai"))
            sales_div = await session.scalar(select(Division).where(Division.name == "Sales"))
            hr_div = await session.scalar(select(Division).where(Division.name == "HR"))

            # Teams (idempotent)
            sales_team = await session.scalar(select(Team).where(Team.name == "FinOpsTestSales"))
            if sales_team is None:
                sales_team = Team(division_id=sales_div.id, name="FinOpsTestSales", created_by="finops_test")
                session.add(sales_team)
                await session.flush()

            hr_team = await session.scalar(select(Team).where(Team.name == "FinOpsTestHR"))
            if hr_team is None:
                hr_team = Team(division_id=hr_div.id, name="FinOpsTestHR", created_by="finops_test")
                session.add(hr_team)
                await session.flush()

            # Team memberships (idempotent)
            andi_tm = await session.scalar(
                select(TeamMember)
                .where(TeamMember.team_id == sales_team.id)
                .where(TeamMember.user_id == andi.id)
            )
            if andi_tm is None:
                session.add(TeamMember(team_id=sales_team.id, user_id=andi.id))

            budi_tm = await session.scalar(
                select(TeamMember)
                .where(TeamMember.team_id == hr_team.id)
                .where(TeamMember.user_id == budi.id)
            )
            if budi_tm is None:
                session.add(TeamMember(team_id=hr_team.id, user_id=budi.id))
            await session.commit()

            now = datetime.now(timezone.utc)

            andi_conv = Conversation(user_id=andi.id, title="Andi finops conv")
            budi_conv = Conversation(user_id=budi.id, title="Budi finops conv")
            session.add(andi_conv)
            session.add(budi_conv)
            await session.flush()

            # 2 assistant messages from Andi (100+150=250 tokens), 1 from Budi (80 tokens)
            session.add(Message(conversation_id=andi_conv.id, role="assistant",
                                content="safe answer 1", tokens=100, latency_ms=200, stop_reason="stop"))
            session.add(Message(conversation_id=andi_conv.id, role="assistant",
                                content="safe answer 2", tokens=150, latency_ms=300, stop_reason="stop"))
            session.add(Message(conversation_id=budi_conv.id, role="assistant",
                                content="safe answer 3", tokens=80, latency_ms=100, stop_reason="stop"))
            # user message — must NOT appear in events
            session.add(Message(conversation_id=andi_conv.id, role="user",
                                content="user question", tokens=None, latency_ms=None, stop_reason=None))
            await session.commit()

            events = await aggregate_spend_events_from_db(
                session,
                window_start=now - timedelta(minutes=1),
                window_end=now + timedelta(minutes=5),
            )

            # 3 assistant messages → 3 events
            assert len(events) == 3

            for e in events:
                assert "user_id" in e
                assert "team_id" in e
                assert "division_id" in e
                assert "bot_id" in e
                assert "cost_usd" in e
                assert "tokens" in e
                # No raw content fields
                assert "content" not in e
                assert "role" not in e
                assert "model" not in e
                assert isinstance(e["cost_usd"], float)
                assert isinstance(e["tokens"], int)

            # Aggregate and verify groupings
            spend = aggregate_spend(events)
            by_user = {e["id"]: e for e in spend["by_user"]}
            assert str(andi.id) in by_user, f"Andi not in by_user: {list(by_user.keys())}"
            assert str(budi.id) in by_user, f"Budi not in by_user: {list(by_user.keys())}"
            assert by_user[str(andi.id)]["tokens"] == 250  # 100 + 150

            by_team = {e["id"]: e for e in spend["by_team"]}
            assert str(sales_team.id) in by_team, f"SalesTeam not in by_team: {list(by_team.keys())}"
            assert str(hr_team.id) in by_team, f"HRTeam not in by_team: {list(by_team.keys())}"

            by_div = {e["id"]: e for e in spend["by_division"]}
            assert str(sales_div.id) in by_div
            assert str(hr_div.id) in by_div

    _migrate()
    asyncio.run(run())


# ---------- 24. DB FinOps: time window boundary ----------

def test_db_finops_spend_window_boundary():
    """Messages outside the time window are excluded from FinOps spend aggregation."""
    import asyncio
    import subprocess
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete, func, select, text

    from e2eai.db import Conversation, Message, User, sessions
    from e2eai.finops import aggregate_spend_events_from_db
    from e2eai.seed import seed_demo

    def _migrate():
        subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True, cwd=".")

    async def run():
        async with sessions()() as session:
            await session.execute(delete(Message))
            await session.execute(delete(Conversation))
            await session.commit()

            await seed_demo(session, password="TestFinOpsDB_1234567")
            andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))

            now = datetime.now(timezone.utc)
            window_start = now - timedelta(minutes=30)
            window_end = now - timedelta(minutes=10)

            conv = Conversation(user_id=andi.id, title="Boundary test conv")
            session.add(conv)
            await session.flush()

            # Message inside the window (backdated via direct SQL)
            msg_in = Message(conversation_id=conv.id, role="assistant",
                             content="in window", tokens=50, latency_ms=100, stop_reason="stop")
            session.add(msg_in)
            await session.flush()
            await session.execute(
                text("UPDATE messages SET created_at = :ts WHERE id = :id"),
                {"ts": window_start + timedelta(minutes=10), "id": str(msg_in.id)},
            )

            # Message outside window (created_at = now, after window_end)
            msg_out = Message(conversation_id=conv.id, role="assistant",
                              content="out of window", tokens=999, latency_ms=999, stop_reason="stop")
            session.add(msg_out)
            await session.commit()

            events = await aggregate_spend_events_from_db(session, window_start, window_end)

            tokens_seen = [e["tokens"] for e in events]
            assert 50 in tokens_seen, "In-window message must be included"
            assert 999 not in tokens_seen, "Out-of-window message must be excluded"

    _migrate()
    asyncio.run(run())


# ---------- 25. DB FinOps: serialization excludes raw content ----------

def test_db_finops_spend_event_serialization_excludes_raw_content():
    """FinOps spend events from DB must not contain content, role, model, or any raw text —
    only safe aggregate fields: user_id, team_id, division_id, bot_id, cost_usd, tokens."""
    import asyncio
    import json
    import subprocess
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete, func, select

    from e2eai.db import Conversation, Message, User, sessions
    from e2eai.finops import aggregate_spend_events_from_db
    from e2eai.seed import seed_demo

    FORBIDDEN_CONTENT = "WhatsApp revenue share is 30 percent"

    def _migrate():
        subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True, cwd=".")

    async def run():
        async with sessions()() as session:
            await session.execute(delete(Message))
            await session.execute(delete(Conversation))
            await session.commit()

            await seed_demo(session, password="TestFinOpsDB_1234567")
            andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
            now = datetime.now(timezone.utc)

            conv = Conversation(user_id=andi.id, title="Safety test conv")
            session.add(conv)
            await session.flush()

            session.add(Message(
                conversation_id=conv.id,
                role="assistant",
                content=FORBIDDEN_CONTENT,
                model="secret-model-xyz",
                tokens=42,
                latency_ms=100,
                stop_reason="stop",
            ))
            await session.commit()

            events = await aggregate_spend_events_from_db(
                session,
                window_start=now - timedelta(minutes=1),
                window_end=now + timedelta(minutes=5),
            )

            assert len(events) >= 1
            for e in events:
                serialized = json.dumps(e)
                assert FORBIDDEN_CONTENT not in serialized, "Raw message content must not appear in event"
                assert "secret-model-xyz" not in serialized, "Model name must not appear in event"
                for forbidden in ("content", "model", "role", "prompt", "answer",
                                  "password", "credential", "bearer", "api_key"):
                    assert forbidden not in serialized.lower(), (
                        f"Forbidden term '{forbidden}' found in FinOps event"
                    )

    _migrate()
    asyncio.run(run())


# ---------- 26. DB FinOps: bot_id groups spend by bot ----------

def test_db_finops_spend_groups_by_bot_id():
    """Conversations with bot_id set produce spend events carrying that bot_id, enabling
    bot-level FinOps aggregation. Conversations without bot_id produce 'unknown' bot_id."""
    import asyncio
    import subprocess
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete, func, select

    from e2eai.db import Bot, Conversation, Message, User, sessions
    from e2eai.finops import aggregate_spend, aggregate_spend_events_from_db
    from e2eai.seed import seed_demo

    def _migrate():
        subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True, cwd=".")

    async def run():
        async with sessions()() as session:
            await session.execute(delete(Message))
            await session.execute(delete(Conversation))
            await session.commit()

            await seed_demo(session, password="TestFinOpsDB_1234567")
            andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
            now = datetime.now(timezone.utc)

            bot = Bot(name="FinOpsTestBot", owner_id=andi.id)
            session.add(bot)
            await session.flush()

            conv_with_bot = Conversation(user_id=andi.id, title="Bot conv", bot_id=bot.id)
            conv_no_bot = Conversation(user_id=andi.id, title="No-bot conv")
            session.add(conv_with_bot)
            session.add(conv_no_bot)
            await session.flush()

            session.add(Message(conversation_id=conv_with_bot.id, role="assistant",
                                content="bot answer", tokens=100, latency_ms=200, stop_reason="stop"))
            session.add(Message(conversation_id=conv_no_bot.id, role="assistant",
                                content="direct answer", tokens=60, latency_ms=150, stop_reason="stop"))
            await session.commit()

            events = await aggregate_spend_events_from_db(
                session,
                window_start=now - timedelta(minutes=1),
                window_end=now + timedelta(minutes=5),
            )

            assert len(events) == 2

            bot_ids = {e["bot_id"] for e in events}
            assert str(bot.id) in bot_ids, f"Bot UUID not in events. bot_ids={bot_ids}"
            assert "unknown" in bot_ids, "No-bot conversation must produce 'unknown' bot_id"

            spend = aggregate_spend(events)
            by_bot = {e["id"]: e for e in spend["by_bot"]}
            assert str(bot.id) in by_bot, f"Bot not in by_bot: {list(by_bot.keys())}"

    _migrate()
    asyncio.run(run())


# ---------- 27. DB FinOps: finops-window API route is wired ----------

def test_finops_window_api_route_is_wired():
    """The GET /api/v1/operate/finops-window endpoint exists in the FastAPI app."""
    from e2eai.main import app

    openapi = app.openapi()
    assert "/api/v1/operate/finops-window" in openapi["paths"]
