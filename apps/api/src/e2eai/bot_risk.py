"""AI risk classification per bot (FR-P2).

Records the governance classification that later release workflows can use to
choose mandatory gates. The mapping is deterministic and stores safe metadata
only in audit records.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .auth import current_session, require_scope
from .bot_release import ReleaseGatePolicy
from .core.errors import AppError
from .db import Bot, BotRiskClassification, User, get_session

VALID_EU_AI_ACT_TIERS = ("minimal", "limited", "high", "unacceptable")


def _safe_profile(profile: dict[str, Any]) -> dict[str, str]:
    return {str(key)[:80]: str(value)[:200] for key, value in (profile or {}).items()}


def _pdp_impact_level(impact: str) -> str:
    text = impact.lower()
    if any(marker in text for marker in ("employee", "identity", "personal", "nik", "email", "phone", "leave")):
        return "personal_data"
    if impact.strip():
        return "non_personal_data"
    return "none"


def gates_for_tier(eu_ai_act_tier: str) -> dict[str, Any]:
    """Map a risk tier to required release-gate settings.

    High-risk bots get the strictest currently implemented gates. Limited-risk bots
    still need zero permission leaks and a basic eval threshold. Minimal-risk bots
    keep the lightweight eval threshold. Unacceptable-risk bots are marked blocked
    so release workflows can refuse them in a later approval slice.
    """
    tier = eu_ai_act_tier.lower().strip()
    if tier not in VALID_EU_AI_ACT_TIERS:
        raise AppError(400, f"Unknown EU AI Act tier: {eu_ai_act_tier}")
    if tier == "high":
        return {
            "eval_threshold": 0.8,
            "require_zero_leaks": True,
            "redteam_pass_rate": 0.95,
            "require_human_signoff": True,
            "compliance_signoff_required": True,
        }
    if tier == "limited":
        return {
            "eval_threshold": 0.75,
            "require_zero_leaks": True,
            "redteam_pass_rate": 0.9,
            "require_human_signoff": False,
            "compliance_signoff_required": False,
        }
    if tier == "unacceptable":
        return {
            "release_blocked": True,
            "compliance_signoff_required": True,
            "require_human_signoff": True,
        }
    return {
        "eval_threshold": 0.7,
        "require_zero_leaks": False,
        "redteam_pass_rate": None,
        "require_human_signoff": False,
        "compliance_signoff_required": False,
    }


async def classify_bot_risk(
    session: AsyncSession,
    *,
    actor: User,
    bot_id: uuid.UUID,
    eu_ai_act_tier: str,
    nist_ai_rmf_profile: dict[str, Any],
    uu_pdp_data_impact: str,
) -> BotRiskClassification:
    """Create or update the FR-P2 risk classification for a bot."""
    bot = await session.get(Bot, bot_id)
    if bot is None:
        raise AppError(404, "Bot not found")

    tier = eu_ai_act_tier.lower().strip()
    required_gates = gates_for_tier(tier)
    pdp_level = _pdp_impact_level(uu_pdp_data_impact)
    row = await session.get(BotRiskClassification, bot_id)
    if row is None:
        row = BotRiskClassification(bot_id=bot_id)
        session.add(row)
    row.eu_ai_act_tier = tier
    row.nist_ai_rmf_profile = _safe_profile(nist_ai_rmf_profile)
    row.uu_pdp_data_impact = str(uu_pdp_data_impact).strip()[:1000]
    row.pdp_impact_level = pdp_level
    row.required_release_gates = required_gates
    row.classified_by = str(actor.id)

    await audit.record(
        session,
        f"user:{actor.id}",
        "bot.risk.classify",
        f"bot:{bot_id}",
        {
            "eu_ai_act_tier": tier,
            "pdp_impact_level": pdp_level,
            "required_gates": sorted(required_gates),
        },
    )
    await session.commit()
    return row


def release_gate_policy_for_risk(classification: BotRiskClassification) -> ReleaseGatePolicy:
    """Build the current release-gate policy from a stored risk classification."""
    gates = classification.required_release_gates or {}
    return ReleaseGatePolicy(
        eval_threshold=gates.get("eval_threshold"),
        require_zero_leaks=bool(gates.get("require_zero_leaks", False)),
        redteam_pass_rate=gates.get("redteam_pass_rate"),
        require_human_signoff=bool(gates.get("require_human_signoff", False)),
    )


def safe_risk_summary(classification: BotRiskClassification) -> dict[str, Any]:
    gates = dict(classification.required_release_gates or {})
    return {
        "bot_id": str(classification.bot_id),
        "eu_ai_act_tier": classification.eu_ai_act_tier,
        "nist_ai_rmf_profile": dict(classification.nist_ai_rmf_profile or {}),
        "uu_pdp_data_impact": classification.uu_pdp_data_impact,
        "pdp_impact_level": classification.pdp_impact_level,
        "required_release_gates": gates,
        "classified_by": classification.classified_by,
        "audit_metadata": {
            "eu_ai_act_tier": classification.eu_ai_act_tier,
            "pdp_impact_level": classification.pdp_impact_level,
            "required_gates": sorted(gates),
        },
    }


class RiskClassificationIn(BaseModel):
    eu_ai_act_tier: str
    nist_ai_rmf_profile: dict[str, Any] = {}
    uu_pdp_data_impact: str = ""


router = APIRouter(prefix="/api/v1/bots", tags=["bot-risk"])


@router.put("/{bot_id}/risk-classification")
async def classify_bot_risk_api(
    bot_id: uuid.UUID,
    body: RiskClassificationIn,
    sess: dict = Depends(current_session),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """FR-P2: classify a bot's AI risk and derive release gates."""
    require_scope(sess, "bots")
    user = await db.get(User, uuid.UUID(sess["user_id"]))
    if user is None:
        raise AppError(401, "Not authenticated")
    classification = await classify_bot_risk(
        db,
        actor=user,
        bot_id=bot_id,
        eu_ai_act_tier=body.eu_ai_act_tier,
        nist_ai_rmf_profile=body.nist_ai_rmf_profile,
        uu_pdp_data_impact=body.uu_pdp_data_impact,
    )
    return safe_risk_summary(classification)
