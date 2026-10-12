"""FR-F11 in-app notification types beyond document sharing.

TDD: tests written before the FR-F11 notification helpers.
"""

import asyncio
import subprocess
import uuid

from sqlalchemy import delete, func, select

from e2eai.db import Notification, User, sessions
from e2eai.notifications import (
    notify_incident_raised,
    notify_release_approved,
    notify_review_assigned,
)
from e2eai.seed import seed_demo


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


async def _reset_notifications(session):
    await session.execute(delete(Notification))
    await session.commit()


async def _demo_users(session):
    await seed_demo(session, password="TestPassword_123456789")
    owner = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))
    andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
    budi = await session.scalar(select(User).where(func.lower(User.email) == "budi@demo.e2eai"))
    assert owner and andi and budi
    owner.status = "active"
    andi.status = "active"
    budi.status = "active"
    await session.commit()
    return owner, andi, budi


def test_fr_f11_remaining_in_app_notification_types_are_created_with_safe_details():
    async def run():
        async with sessions()() as session:
            await _reset_notifications(session)
            owner, andi, budi = await _demo_users(session)

            review_id = uuid.uuid4()
            bot_id = uuid.uuid4()
            incident_id = uuid.uuid4()

            await notify_review_assigned(
                session,
                actor=owner,
                reviewer=andi,
                review_type="eval_item",
                target_id=review_id,
                title="Safety review queue",
                priority="high",
                unsafe_context="raw prompt: customer_secret_token_1234567890",
            )
            await notify_release_approved(
                session,
                actor=owner,
                recipient=andi,
                bot_id=bot_id,
                bot_name="HR Policy Bot",
                version=3,
                environment="prod",
                approval_id=uuid.uuid4(),
            )
            await notify_incident_raised(
                session,
                actor=owner,
                recipients=[andi, budi],
                incident_id=incident_id,
                severity="high",
                title="Retrieval latency incident",
                source="manual",
                unsafe_description="full trace contains bearer token customer_secret_token_1234567890",
            )

            rows = (await session.execute(select(Notification).order_by(Notification.kind, Notification.user_id))).scalars().all()
            assert [n.kind for n in rows] == [
                "incident.raised",
                "incident.raised",
                "release.approved",
                "review.assigned",
            ]

            by_kind = {n.kind: n for n in rows if n.user_id == andi.id}
            assert by_kind["review.assigned"].details == {
                "review_type": "eval_item",
                "target_id": str(review_id),
                "title": "Safety review queue",
                "assigned_by": str(owner.id),
                "priority": "high",
            }
            assert by_kind["release.approved"].details == {
                "bot_id": str(bot_id),
                "bot_name": "HR Policy Bot",
                "version": 3,
                "environment": "prod",
                "approved_by": str(owner.id),
                "approval_id": by_kind["release.approved"].details["approval_id"],
            }
            assert by_kind["incident.raised"].details == {
                "incident_id": str(incident_id),
                "severity": "high",
                "title": "Retrieval latency incident",
                "source": "manual",
                "raised_by": str(owner.id),
            }

            serialized = "\n".join(str(n.details) for n in rows)
            assert "customer_secret_token" not in serialized
            assert "raw prompt" not in serialized
            assert "bearer token" not in serialized

    _migrate()
    asyncio.run(run())


def test_fr_f11_notification_helpers_do_not_notify_actor_or_inactive_users():
    async def run():
        async with sessions()() as session:
            await _reset_notifications(session)
            owner, andi, _budi = await _demo_users(session)
            andi.status = "disabled"
            await session.commit()

            await notify_incident_raised(
                session,
                actor=owner,
                recipients=[owner, andi],
                incident_id=uuid.uuid4(),
                severity="medium",
                title="Guardrail incident",
            )

            assert (await session.execute(select(Notification))).scalars().all() == []
            andi.status = "active"
            await session.commit()

    _migrate()
    asyncio.run(run())
