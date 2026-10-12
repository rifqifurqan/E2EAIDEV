"""FR-P1 use-case intake form: problem, users, success metrics, data sources,
and systems to integrate.

The intake slice is deterministic/offline: it stores planning metadata only,
emits audit events, and returns secret-safe summaries suitable for the Plan UI.
"""

import asyncio
import subprocess

import pytest
from sqlalchemy import delete, func, select


REQUIRED_METRICS = {
    "task_success": "Resolve 80% of pricing questions with cited answers",
    "deflection": "Deflect 30% of repetitive sales-support tickets",
    "time_saved": "Save 10 minutes per answered request",
}


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


def test_create_use_case_intake_captures_required_fr_p1_fields_and_audits():
    """A planner can submit problem, users, required success metrics, data sources,
    and systems to integrate; the stored/output record preserves only safe metadata.
    """

    async def run():
        from e2eai.db import AuditEntry, UseCaseIntake, User, sessions
        from e2eai.plan_intake import create_use_case_intake, safe_use_case_summary
        from e2eai.seed import seed_demo

        async with sessions()() as session:
            await session.execute(delete(UseCaseIntake))
            await session.commit()
            await seed_demo(session, password="TestPassword_123456789")
            actor = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))

            intake = await create_use_case_intake(
                session,
                actor=actor,
                title="Sales policy assistant",
                problem="Sales teams need cited answers about partnership terms.",
                users=["Sales reps", "Sales managers"],
                success_metrics=REQUIRED_METRICS,
                data_sources=["Partnership contracts", "Sales playbooks"],
                systems_to_integrate=["Odoo CRM", "Talenta HR"],
            )

            assert intake.id is not None
            assert intake.owner_id == actor.id
            assert intake.problem.startswith("Sales teams")
            assert intake.users == ["Sales reps", "Sales managers"]
            assert intake.success_metrics == REQUIRED_METRICS
            assert intake.data_sources == ["Partnership contracts", "Sales playbooks"]
            assert intake.systems_to_integrate == ["Odoo CRM", "Talenta HR"]

            summary = safe_use_case_summary(intake)
            assert summary["problem"] == intake.problem
            assert summary["success_metrics"]["task_success"] == REQUIRED_METRICS["task_success"]
            assert summary["data_sources"] == ["Partnership contracts", "Sales playbooks"]
            assert summary["systems_to_integrate"] == ["Odoo CRM", "Talenta HR"]
            assert "password" not in str(summary).lower()
            assert "secret" not in str(summary).lower()
            assert "token" not in str(summary).lower()

            audit = await session.scalar(
                select(AuditEntry).where(AuditEntry.action == "plan.use_case_intake.create")
            )
            assert audit is not None
            assert audit.details["metrics"] == sorted(REQUIRED_METRICS)
            assert "Sales teams" not in str(audit.details)  # audit stores metadata, not raw problem text

    _migrate()
    asyncio.run(run())


def test_use_case_intake_requires_all_success_metric_categories():
    """FR-P1 explicitly requires task success, deflection, and time-saved metrics."""

    async def run():
        from e2eai.core.errors import AppError
        from e2eai.db import UseCaseIntake, User, sessions
        from e2eai.plan_intake import create_use_case_intake
        from e2eai.seed import seed_demo

        async with sessions()() as session:
            await session.execute(delete(UseCaseIntake))
            await session.commit()
            await seed_demo(session, password="TestPassword_123456789")
            actor = await session.scalar(select(User).where(func.lower(User.email) == "intern@demo.e2eai"))

            with pytest.raises(AppError) as exc:
                await create_use_case_intake(
                    session,
                    actor=actor,
                    title="Incomplete intake",
                    problem="Need help deciding what to automate.",
                    users=["AI PM"],
                    success_metrics={"task_success": "Improve task success"},
                    data_sources=["Support tickets"],
                    systems_to_integrate=[],
                )

            assert exc.value.status == 400
            assert "deflection" in exc.value.title
            assert "time_saved" in exc.value.title

    _migrate()
    asyncio.run(run())


def test_use_case_intake_api_route_is_wired():
    """The Plan-stage intake form API is exposed in the FastAPI app."""
    from e2eai.main import app

    paths = app.openapi()["paths"]
    assert "/api/v1/plan/use-cases" in paths
    assert "post" in paths["/api/v1/plan/use-cases"]
