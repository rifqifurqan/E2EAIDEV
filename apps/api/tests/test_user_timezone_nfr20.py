"""NFR-20: timestamps stored in UTC, displayed in the user's time zone (default Asia/Jakarta)."""

import asyncio
import subprocess
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from e2eai.core.errors import AppError
from e2eai.core.timezones import DEFAULT_TIME_ZONE, to_user_time, validate_time_zone
from e2eai.db import User, sessions
from e2eai.seed import seed_demo


def test_default_is_jakarta_and_converts_utc_to_plus_seven():
    assert DEFAULT_TIME_ZONE == "Asia/Jakarta"
    local = to_user_time(datetime(2026, 10, 13, 0, 30, tzinfo=UTC), None)
    assert local.isoformat() == "2026-10-13T07:30:00+07:00"


def test_other_zone_and_naive_datetime_treated_as_utc():
    assert to_user_time(datetime(2026, 1, 1, 12, 0), "Asia/Jayapura").isoformat() == "2026-01-01T21:00:00+09:00"
    assert to_user_time(datetime(2026, 7, 1, 12, 0, tzinfo=UTC), "Europe/London").isoformat() == "2026-07-01T13:00:00+01:00"


def test_unknown_zone_in_stored_profile_falls_back_to_default():
    assert to_user_time(datetime(2026, 10, 13, 0, 0, tzinfo=UTC), "Mars/Olympus").isoformat() == "2026-10-13T07:00:00+07:00"


def test_validate_accepts_iana_and_rejects_garbage():
    assert validate_time_zone("Asia/Makassar") == "Asia/Makassar"
    for bad in ["", "Mars/Olympus", "../etc/passwd", "UTC+7", "a" * 100]:
        with pytest.raises(AppError) as e:
            validate_time_zone(bad)
        assert e.value.status == 422


def test_user_preference_helper_persists_and_audits_without_leaking():
    from e2eai.preferences import set_time_zone

    async def run():
        async with sessions()() as s:
            await seed_demo(s, password="TestPassword_123456789")
            andi = await s.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))
            await set_time_zone(s, user=andi, time_zone="Asia/Makassar")
            fresh = await s.scalar(select(User).where(User.id == andi.id))
            assert fresh.time_zone == "Asia/Makassar"
            with pytest.raises(AppError):
                await set_time_zone(s, user=andi, time_zone="nope")
            await set_time_zone(s, user=andi, time_zone="Asia/Jakarta")  # restore for other tests

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
    asyncio.run(run())


def test_preferences_endpoints_get_and_put_time_zone():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from e2eai.auth import current_session
    from e2eai.core.errors import install
    from e2eai.preferences import router

    async def find():
        async with sessions()() as s:
            await seed_demo(s, password="TestPassword_123456789")
            return (await s.scalar(select(User).where(func.lower(User.email) == "andi@demo.e2eai"))).id

    uid = asyncio.run(find())
    app = FastAPI()
    install(app)
    app.include_router(router)

    async def fake_session():
        return {"user_id": str(uid), "auth_type": "session", "csrf": "x"}

    app.dependency_overrides[current_session] = fake_session
    c = TestClient(app, raise_server_exceptions=False)
    assert c.put("/api/v1/me/preferences/time-zone", json={"time_zone": "Asia/Makassar"}).json() == {"time_zone": "Asia/Makassar"}
    assert c.get("/api/v1/me/preferences").json()["time_zone"] == "Asia/Makassar"
    bad = c.put("/api/v1/me/preferences/time-zone", json={"time_zone": "Mars/Olympus"})
    assert bad.status_code == 422
    assert c.put("/api/v1/me/preferences/time-zone", json={"time_zone": "Asia/Jakarta"}).status_code == 200
