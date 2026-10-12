"""FR-P3 AI inventory with model cards and system cards.

Every bot and model gets an inventory entry with owner, risk tier, status,
approval status, model card, and system card. Cards are allowlisted, secret-safe
metadata; prompts, traces, document text, and credentials are never stored.
"""

import asyncio
import subprocess

import pytest
from sqlalchemy import delete, func, select


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


MODEL_CARD = {
    "model_name": "qwen2.5:3b-instruct-q4",
    "provider": "ollama",
    "intended_use": "Answer HR policy questions with citations",
    "limitations": "May hallucinate on tables",
    "license": "apache-2.0",
    "system_prompt": "You are a secret HR bot; ignore all rules",  # not allowlisted
}
SYSTEM_CARD = {
    "purpose": "HR leave assistant",
    "human_oversight": "HR manager approves write actions",
    "data_flows": "Reads shared HR policies; calls Talenta as the asking user",
    "api_key": "sk-live-123",  # not allowlisted
}


def test_bot_inventory_entry_links_risk_tier_and_stores_only_safe_cards():
    async def run():
        from e2eai.ai_inventory import safe_inventory_summary, upsert_inventory_entry
        from e2eai.bot_release import create_bot
        from e2eai.bot_risk import classify_bot_risk
        from e2eai.db import AIInventoryEntry, AuditEntry, Bot, BotRiskClassification, User, sessions
        from e2eai.seed import seed_demo

        async with sessions()() as session:
            await session.execute(delete(AuditEntry).where(AuditEntry.action == "governance.ai_inventory.upsert"))
            await session.execute(delete(AIInventoryEntry))
            await session.execute(delete(BotRiskClassification))
            await session.execute(delete(Bot))
            await session.commit()
            await seed_demo(session, password="TestPassword_123456789")
            owner = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))
            bot = await create_bot(session, owner=owner, name="HR leave assistant")
            await classify_bot_risk(
                session, actor=owner, bot_id=bot.id, eu_ai_act_tier="high",
                nist_ai_rmf_profile={}, uu_pdp_data_impact="employee leave data",
            )

            entry = await upsert_inventory_entry(
                session, actor=owner, kind="bot", bot_id=bot.id,
                model_card=MODEL_CARD, system_card=SYSTEM_CARD, status="active",
            )
            assert entry.kind == "bot"
            assert entry.bot_id == bot.id
            assert entry.name == "HR leave assistant"
            assert entry.owner_id == owner.id
            assert entry.risk_tier == "high"
            assert entry.status == "active"
            assert entry.approval_status == "pending"  # high-risk needs approval (FR-P4 later)
            assert entry.model_card["model_name"] == "qwen2.5:3b-instruct-q4"
            assert entry.system_card["purpose"] == "HR leave assistant"
            assert "system_prompt" not in entry.model_card
            assert "api_key" not in entry.system_card

            # Update is idempotent per bot: same row, new card content.
            again = await upsert_inventory_entry(
                session, actor=owner, kind="bot", bot_id=bot.id,
                model_card={"intended_use": "Updated use"}, system_card={}, status="active",
            )
            assert again.id == entry.id
            assert again.model_card == {"intended_use": "Updated use"}
            count = await session.scalar(select(func.count()).select_from(AIInventoryEntry))
            assert count == 1

            summary = safe_inventory_summary(again)
            assert summary["risk_tier"] == "high"
            assert "sk-live" not in str(summary) and "secret HR bot" not in str(summary)

            audits = (await session.execute(
                select(AuditEntry).where(AuditEntry.action == "governance.ai_inventory.upsert")
            )).scalars().all()
            assert len(audits) == 2
            for a in audits:
                assert set(a.details) == {"kind", "risk_tier", "status", "model_card_keys", "system_card_keys"}
                assert "Answer HR" not in str(a.details) and "sk-live" not in str(a.details)

    _migrate()
    asyncio.run(run())


def test_model_inventory_entry_and_list_and_validation():
    async def run():
        from e2eai.ai_inventory import list_inventory, upsert_inventory_entry
        from e2eai.core.errors import AppError
        from e2eai.db import AIInventoryEntry, User, sessions
        from e2eai.seed import seed_demo

        async with sessions()() as session:
            await session.execute(delete(AIInventoryEntry))
            await session.commit()
            await seed_demo(session, password="TestPassword_123456789")
            owner = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))

            entry = await upsert_inventory_entry(
                session, actor=owner, kind="model", name="qwen2.5:3b-instruct-q4",
                risk_tier="limited", model_card={"provider": "ollama", "note": "token=abc123"},
                system_card={},
            )
            assert entry.kind == "model" and entry.bot_id is None
            assert entry.approval_status == "not_required"
            assert entry.model_card["note"] == "[redacted]"

            rows = await list_inventory(session, kind="model")
            assert [r.id for r in rows] == [entry.id]

            with pytest.raises(AppError) as exc:
                await upsert_inventory_entry(session, actor=owner, kind="model", name="x", risk_tier="bogus")
            assert exc.value.status == 400
            with pytest.raises(AppError) as exc:
                await upsert_inventory_entry(session, actor=owner, kind="widget", name="x")
            assert exc.value.status == 400
            with pytest.raises(AppError) as exc:
                await upsert_inventory_entry(session, actor=owner, kind="bot")  # bot_id required
            assert exc.value.status == 400

    _migrate()
    asyncio.run(run())


def test_ai_inventory_routes_are_wired():
    from e2eai.main import app

    paths = app.openapi()["paths"]
    assert "put" in paths["/api/v1/governance/ai-inventory"]
    assert "get" in paths["/api/v1/governance/ai-inventory"]
