"""FR-P2 AI risk classification per bot.

Classification records EU AI Act tier, NIST AI RMF profile, and UU PDP data
impact. The tier maps to release-gate requirements without storing raw prompts,
answers, documents, or credentials.
"""

import asyncio
import subprocess

from sqlalchemy import delete, func, select


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


def test_high_risk_bot_classification_sets_required_release_gates_and_audits():
    """High-risk bots require eval threshold, zero leaks, red-team pass, and human sign-off."""

    async def run():
        from e2eai.bot_release import create_bot
        from e2eai.bot_risk import classify_bot_risk, release_gate_policy_for_risk, safe_risk_summary
        from e2eai.db import AuditEntry, Bot, BotRiskClassification, User, sessions
        from e2eai.seed import seed_demo

        async with sessions()() as session:
            await session.execute(delete(BotRiskClassification))
            await session.execute(delete(Bot))
            await session.commit()
            await seed_demo(session, password="TestPassword_123456789")
            owner = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))
            bot = await create_bot(session, owner=owner, name="HR leave assistant")

            classification = await classify_bot_risk(
                session,
                actor=owner,
                bot_id=bot.id,
                eu_ai_act_tier="high",
                nist_ai_rmf_profile={"govern": "mapped", "measure": "required"},
                uu_pdp_data_impact="processes employee leave and identity data",
            )

            assert classification.bot_id == bot.id
            assert classification.eu_ai_act_tier == "high"
            assert classification.nist_ai_rmf_profile == {"govern": "mapped", "measure": "required"}
            assert classification.uu_pdp_data_impact == "processes employee leave and identity data"
            assert classification.required_release_gates == {
                "eval_threshold": 0.8,
                "require_zero_leaks": True,
                "redteam_pass_rate": 0.95,
                "require_human_signoff": True,
                "compliance_signoff_required": True,
            }

            policy = release_gate_policy_for_risk(classification)
            assert policy.eval_threshold == 0.8
            assert policy.require_zero_leaks is True
            assert policy.redteam_pass_rate == 0.95
            assert policy.require_human_signoff is True

            summary = safe_risk_summary(classification)
            assert summary["bot_id"] == str(bot.id)
            assert summary["required_release_gates"]["compliance_signoff_required"] is True
            assert "employee leave" not in str(summary["audit_metadata"])

            audit = await session.scalar(
                select(AuditEntry).where(AuditEntry.action == "bot.risk.classify")
            )
            assert audit is not None
            assert audit.details == {
                "eu_ai_act_tier": "high",
                "pdp_impact_level": "personal_data",
                "required_gates": sorted(classification.required_release_gates),
            }

    _migrate()
    asyncio.run(run())


def test_risk_classification_api_route_is_wired():
    """The bot risk-classification endpoint is exposed."""
    from e2eai.main import app

    paths = app.openapi()["paths"]
    assert "/api/v1/bots/{bot_id}/risk-classification" in paths
    assert "put" in paths["/api/v1/bots/{bot_id}/risk-classification"]
