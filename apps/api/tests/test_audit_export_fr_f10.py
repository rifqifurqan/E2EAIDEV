"""FR-F10 audit log export to SIEM.

Exports hash-chained audit rows to syslog, OpenTelemetry log records, or webhook
JSON payloads without exposing stack traces, secrets, or raw credentials.
"""

import asyncio
import subprocess

from sqlalchemy import delete, select


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


def test_audit_export_formats_syslog_otel_and_webhook_payloads_without_secrets():
    async def run():
        from e2eai import audit
        from e2eai.audit_export import export_audit_events
        from e2eai.db import AuditEntry, sessions

        async with sessions()() as session:
            await session.execute(delete(AuditEntry))
            await session.commit()
            await audit.record(
                session,
                "user:123",
                "document.share",
                "document:abc",
                {"permission": "viewer", "token": "secret-token", "password": "p@ss"},
            )
            await session.commit()

            row = await session.scalar(select(AuditEntry))
            syslog = await export_audit_events(session, sink="syslog")
            assert syslog["cursor"] == row.seq
            assert syslog["has_more"] is False
            assert len(syslog["events"]) == 1
            line = syslog["events"][0]
            assert "e2eai audit action=document.share actor=user:123 target=document:abc" in line
            assert "token" not in line.lower() and "password" not in line.lower() and "secret-token" not in line

            otel = await export_audit_events(session, sink="otel")
            record = otel["events"][0]
            assert record["body"] == "document.share"
            assert record["attributes"]["audit.hash"]
            assert record["attributes"]["audit.seq"] == row.seq
            assert record["attributes"]["audit.detail_keys"] == ["password", "permission", "token"]
            assert "secret-token" not in str(record)

            webhook = await export_audit_events(session, sink="webhook", after_seq=row.seq)
            assert webhook == {"sink": "webhook", "cursor": row.seq, "has_more": False, "events": []}

    _migrate()
    asyncio.run(run())


def test_audit_export_route_is_wired():
    from e2eai.main import app

    paths = app.openapi()["paths"]
    assert "post" in paths["/api/v1/audit/export"]
