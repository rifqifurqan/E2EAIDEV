"""FR-F17 secret and certificate rotation.

API keys rotate without downtime (new key issued, old key keeps working for a short
grace window), a leaked key can be revoked immediately, generated secrets follow the
project charset rules, and certificates warn 14 days before expiry. No raw secrets are
audited or returned by status helpers.
"""

import asyncio
import subprocess
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


def test_generate_secret_follows_charset_and_length_rules():
    from e2eai.secret_rotation import generate_secret

    seen = set()
    for _ in range(20):
        value = generate_secret()
        assert len(value) >= 16
        assert set(value) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._~-")
        seen.add(value)
    assert len(seen) == 20
    with pytest.raises(ValueError):
        generate_secret(8)


def test_certificate_status_warns_14_days_before_expiry():
    from e2eai.secret_rotation import certificate_status

    now = datetime(2026, 10, 12, tzinfo=UTC)
    assert certificate_status(now + timedelta(days=60), now=now)["state"] == "ok"
    warn = certificate_status(now + timedelta(days=14), now=now)
    assert warn["state"] == "expiring"
    assert warn["days_left"] == 14
    assert certificate_status(now + timedelta(days=3), now=now)["state"] == "expiring"
    expired = certificate_status(now - timedelta(days=1), now=now)
    assert expired["state"] == "expired"
    assert expired["days_left"] < 0


def test_rotation_plan_lists_zero_downtime_steps_without_secret_values():
    from e2eai.secret_rotation import build_rotation_plan

    plan = build_rotation_plan(["litellm_master_key", "db_password", "oidc_client_secret"])
    names = [step["secret"] for step in plan["steps"]]
    assert names == ["litellm_master_key", "db_password", "oidc_client_secret"]
    for step in plan["steps"]:
        assert step["strategy"] in {"dual-key-overlap", "dual-credential-overlap"}
        assert "value" not in step
    with pytest.raises(ValueError):
        build_rotation_plan(["not_a_known_secret"])


def test_rotate_api_key_overlaps_then_emergency_revoke_is_immediate_and_audited():
    async def run():
        from e2eai.api_keys import authenticate_api_key, create_api_key
        from e2eai.db import ApiKey, AuditEntry, User, sessions
        from e2eai.seed import seed_demo
        from e2eai.secret_rotation import emergency_revoke_api_key, rotate_api_key

        async with sessions()() as session:
            await session.execute(delete(AuditEntry).where(AuditEntry.action.like("secret.%")))
            await session.execute(delete(ApiKey))
            await session.commit()
            await seed_demo(session, password="TestPassword_123456789")
            andi = await session.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
            old = await create_api_key(session, user=andi, name="ci", scopes=["chat"])

            new = await rotate_api_key(session, user=andi, key_id=old["id"], grace_minutes=10)
            assert new["raw_key"] != old["raw_key"]
            assert new["scopes"] == ["chat"]
            assert new["name"] == "ci"
            assert new["old_key_expires_at"]

            # zero downtime: both keys authenticate during the grace window
            assert await authenticate_api_key(session, old["raw_key"]) is not None
            assert await authenticate_api_key(session, new["raw_key"]) is not None

            # grace elapsed -> old key stops working, new key keeps working
            old_row = await session.get(ApiKey, __import__("uuid").UUID(old["id"]))
            old_row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()
            assert await authenticate_api_key(session, old["raw_key"]) is None
            assert await authenticate_api_key(session, new["raw_key"]) is not None

            # emergency revoke: effective immediately (<5 min requirement)
            admin_audit = await emergency_revoke_api_key(session, actor_id="user:admin", key_id=new["id"], reason="leaked in CI log")
            assert admin_audit["status"] == "revoked"
            assert await authenticate_api_key(session, new["raw_key"]) is None

            audits = (await session.execute(
                select(AuditEntry).where(AuditEntry.action.like("secret.%")).order_by(AuditEntry.seq)
            )).scalars().all()
            assert [a.action for a in audits] == ["secret.api_key.rotate", "secret.api_key.emergency_revoke"]
            blob = str(audits)
            for audit in audits:
                blob += str(audit.details)
            assert new["raw_key"] not in blob and old["raw_key"] not in blob

    _migrate()
    asyncio.run(run())


def test_rotation_routes_are_wired():
    from e2eai.main import app

    paths = app.openapi()["paths"]
    assert "post" in paths["/api/v1/security/api-keys/{key_id}/rotate"]
    assert "post" in paths["/api/v1/security/api-keys/{key_id}/emergency-revoke"]
    assert "post" in paths["/api/v1/security/certificate-status"]
    assert "post" in paths["/api/v1/security/rotation-plan"]
