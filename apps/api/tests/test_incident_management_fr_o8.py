"""FR-O8 AI incident management: report -> severity -> linked traces -> fix -> release -> post-incident record.

Deterministic/offline. Incidents carry ids, labels, and redacted free text; credentials are never stored.
"""

import asyncio
import subprocess

import pytest
from sqlalchemy import delete, func, select

from e2eai.core.errors import AppError
from e2eai.db import AuditEntry, User, sessions
from e2eai.seed import ADMIN_EMAIL, bootstrap_admin, seed_demo


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


async def _people(session):
    from e2eai.db import AIIncident

    await session.execute(delete(AuditEntry).where(AuditEntry.action.like("incident.%")))
    await session.execute(delete(AIIncident))
    await session.commit()
    await seed_demo(session, password="TestPassword_123456789")
    await bootstrap_admin(session, password="TestPassword_123456789")
    admin = await session.scalar(select(User).where(func.lower(User.email) == ADMIN_EMAIL))
    andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
    return admin, andi


def test_report_sets_severity_links_traces_and_redacts():
    async def run():
        from e2eai.incidents import report_incident

        async with sessions()() as session:
            admin, andi = await _people(session)
            inc = await report_incident(
                session, actor=andi, title="Bot leaked a salary figure", severity="sev1",
                description="Answer showed numbers. api_key=sk-abc123 was in the output", trace_ids=["tr-1", "tr-2", "tr-1"],
                bot_id=None,
            )
            assert inc.status == "reported" and inc.severity == "sev1"
            assert inc.trace_ids == ["tr-1", "tr-2"]  # de-duplicated, order kept
            assert "sk-abc123" not in inc.description and "[redacted]" in inc.description
            assert inc.reported_by == str(andi.id)

            with pytest.raises(AppError) as exc:
                await report_incident(session, actor=andi, title="x", severity="critical", description="", trace_ids=[])
            assert exc.value.status == 400
            with pytest.raises(AppError) as exc:  # trace ids must be plain ids, not content
                await report_incident(
                    session, actor=andi, title="x", severity="sev3", description="", trace_ids=["what is the CEO salary?"]
                )
            assert exc.value.status == 400

    _migrate()
    asyncio.run(run())


def test_lifecycle_requires_admin_fix_release_and_postmortem_to_close():
    async def run():
        from e2eai.incidents import add_traces, record_postmortem, report_incident, transition_incident

        async with sessions()() as session:
            admin, andi = await _people(session)
            inc = await report_incident(session, actor=andi, title="Hallucinated policy", severity="sev2", description="", trace_ids=[])

            with pytest.raises(AppError) as exc:  # non-admin cannot triage
                await transition_incident(session, actor=andi, incident_id=inc.id, to_status="triaged")
            assert exc.value.status == 403

            with pytest.raises(AppError) as exc:  # cannot skip states
                await transition_incident(session, actor=admin, incident_id=inc.id, to_status="released")
            assert exc.value.status == 409

            await transition_incident(session, actor=admin, incident_id=inc.id, to_status="triaged", assignee_id=str(admin.id))
            await add_traces(session, actor=andi, incident_id=inc.id, trace_ids=["tr-9"])
            inc = await transition_incident(session, actor=admin, incident_id=inc.id, to_status="fixing")

            with pytest.raises(AppError) as exc:  # fixed needs fix notes
                await transition_incident(session, actor=admin, incident_id=inc.id, to_status="fixed")
            assert exc.value.status == 400
            await transition_incident(session, actor=admin, incident_id=inc.id, to_status="fixed", fix_notes="Re-indexed policy doc")

            with pytest.raises(AppError) as exc:  # released needs the bundle/version that carries the fix
                await transition_incident(session, actor=admin, incident_id=inc.id, to_status="released")
            assert exc.value.status == 400
            await transition_incident(session, actor=admin, incident_id=inc.id, to_status="released", release_ref="hr-bot@v7")

            with pytest.raises(AppError) as exc:  # closing needs the post-incident record
                await transition_incident(session, actor=admin, incident_id=inc.id, to_status="closed")
            assert exc.value.status == 409
            await record_postmortem(
                session, actor=admin, incident_id=inc.id,
                summary="Stale doc indexed", root_cause="Missing review expiry", lessons=["Enable FR-D8 expiry"],
                action_items=["Add freshness check"],
            )
            closed = await transition_incident(session, actor=admin, incident_id=inc.id, to_status="closed")
            assert closed.status == "closed" and closed.closed_at is not None
            assert closed.trace_ids == ["tr-9"] and closed.release_ref == "hr-bot@v7"
            assert closed.postmortem["root_cause"] == "Missing review expiry"

            actions = set(
                (await session.scalars(select(AuditEntry.action).where(AuditEntry.action.like("incident.%")))).all()
            )
            assert {"incident.report", "incident.transition", "incident.postmortem", "incident.traces"} <= actions

    _migrate()
    asyncio.run(run())


def test_report_notifies_admins_and_listing_filters_by_status():
    async def run():
        from sqlalchemy import select as sel

        from e2eai.db import Notification
        from e2eai.incidents import list_incidents, report_incident

        async with sessions()() as session:
            admin, andi = await _people(session)
            await session.execute(delete(Notification).where(Notification.kind == "incident.raised"))
            await session.commit()
            inc = await report_incident(session, actor=andi, title="Toxic output", severity="sev2", description="", trace_ids=[])
            kinds = (await session.scalars(sel(Notification.kind).where(Notification.user_id == admin.id))).all()
            assert "incident.raised" in kinds
            rows = await list_incidents(session, status="reported")
            assert [r["id"] for r in rows] == [str(inc.id)]
            assert await list_incidents(session, status="closed") == []

    _migrate()
    asyncio.run(run())


def test_routes_are_wired():
    from e2eai.main import app

    paths = app.openapi()["paths"]
    assert "post" in paths["/api/v1/incidents"] and "get" in paths["/api/v1/incidents"]
    assert "post" in paths["/api/v1/incidents/{incident_id}/transition"]
    assert "post" in paths["/api/v1/incidents/{incident_id}/postmortem"]
    assert "post" in paths["/api/v1/incidents/{incident_id}/traces"]
