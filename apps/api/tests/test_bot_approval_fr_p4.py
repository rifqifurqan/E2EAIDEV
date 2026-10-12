"""FR-P4 approval workflow for high-risk bots.

High-risk bot releases need a compliance approval workflow before release. The
workflow stores safe governance metadata only, updates the AI inventory approval
state, and audits decisions without raw prompts, traces, document text, or
credentials.
"""

import asyncio
import subprocess

import pytest
from sqlalchemy import delete, func, select


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


def test_high_risk_bot_approval_request_and_decision_updates_inventory_and_audits():
    async def run():
        from e2eai.ai_inventory import upsert_inventory_entry
        from e2eai.bot_approval import decide_bot_approval, request_bot_approval, safe_approval_summary
        from e2eai.bot_release import create_bot
        from e2eai.bot_risk import classify_bot_risk
        from e2eai.db import AIInventoryEntry, AuditEntry, Bot, BotApproval, BotRiskClassification, User, sessions
        from e2eai.seed import seed_demo

        async with sessions()() as session:
            await session.execute(delete(AuditEntry).where(AuditEntry.action.like("governance.bot_approval.%")))
            await session.execute(delete(BotApproval))
            await session.execute(delete(AIInventoryEntry))
            await session.execute(delete(BotRiskClassification))
            await session.execute(delete(Bot))
            await session.commit()
            await seed_demo(session, password="TestPassword_123456789")
            owner = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))
            approver = await session.scalar(select(User).where(func.lower(User.email) == "budi@demo.e2eai"))
            bot = await create_bot(session, owner=owner, name="HR leave assistant")
            await classify_bot_risk(
                session,
                actor=owner,
                bot_id=bot.id,
                eu_ai_act_tier="high",
                nist_ai_rmf_profile={},
                uu_pdp_data_impact="employee leave data",
            )
            inventory = await upsert_inventory_entry(session, actor=owner, kind="bot", bot_id=bot.id, status="active")
            assert inventory.approval_status == "pending"

            approval = await request_bot_approval(
                session,
                actor=owner,
                bot_id=bot.id,
                rationale="Ready for HR release with token=abc123 in accidental note",
            )
            assert approval.bot_id == bot.id
            assert approval.status == "pending"
            assert approval.risk_tier == "high"
            assert approval.rationale == "[redacted]"

            decided = await decide_bot_approval(
                session,
                actor=approver,
                approval_id=approval.id,
                decision="approved",
                note="Approved after compliance review",
            )
            assert decided.id == approval.id
            assert decided.status == "approved"
            assert decided.decided_by == str(approver.id)
            assert decided.decision_note == "Approved after compliance review"

            refreshed_inventory = await session.get(AIInventoryEntry, inventory.id)
            assert refreshed_inventory.approval_status == "approved"

            summary = safe_approval_summary(decided)
            assert summary["status"] == "approved"
            assert summary["risk_tier"] == "high"
            assert "token=abc123" not in str(summary)

            audits = (await session.execute(
                select(AuditEntry).where(AuditEntry.action.like("governance.bot_approval.%"))
            )).scalars().all()
            assert [a.action for a in audits] == ["governance.bot_approval.request", "governance.bot_approval.decide"]
            for audit in audits:
                assert "token=abc123" not in str(audit.details)
                assert set(audit.details) <= {"approval_id", "bot_id", "decision", "risk_tier", "status"}

    _migrate()
    asyncio.run(run())


def test_bot_approval_validation_and_routes_are_wired():
    async def run():
        from e2eai.bot_approval import decide_bot_approval, request_bot_approval
        from e2eai.bot_release import create_bot
        from e2eai.core.errors import AppError
        from e2eai.db import Bot, BotApproval, BotRiskClassification, User, sessions
        from e2eai.seed import seed_demo

        async with sessions()() as session:
            await session.execute(delete(BotApproval))
            await session.execute(delete(BotRiskClassification))
            await session.execute(delete(Bot))
            await session.commit()
            await seed_demo(session, password="TestPassword_123456789")
            owner = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))
            bot = await create_bot(session, owner=owner, name="Low risk helper")

            approval = await request_bot_approval(session, actor=owner, bot_id=bot.id)
            with pytest.raises(AppError) as exc:
                await decide_bot_approval(session, actor=owner, approval_id=approval.id, decision="maybe")
            assert exc.value.status == 400
            with pytest.raises(AppError) as exc:
                await request_bot_approval(session, actor=owner, bot_id=bot.id, approval_type="unsupported")
            assert exc.value.status == 400

    _migrate()
    asyncio.run(run())

    from e2eai.main import app

    paths = app.openapi()["paths"]
    assert "post" in paths["/api/v1/governance/bot-approvals"]
    assert "post" in paths["/api/v1/governance/bot-approvals/{approval_id}/decisions"]
    assert "get" in paths["/api/v1/governance/bot-approvals"]
