"""TDD tests for the reset-admin-password operator command (UAT-ADMIN-001).

These tests verify:
1. seed.reset_admin_password exists and has the right signature.
2. manage.py exposes a reset-admin-password CLI command.
3. The --creds-file option writes email and password (not the hash) to a file.
4. The credentials file is never inside the repo tree.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from pydantic import TypeAdapter, EmailStr

from e2eai.seed import ADMIN_EMAIL, gen_password, reset_admin_password

runner = CliRunner()


# ── 1. seed.reset_admin_password contract ────────────────────────────────────

def test_admin_email_is_accepted_by_login_schema():
    """The operator admin email must be browser/API-login compatible."""
    assert TypeAdapter(EmailStr).validate_python(ADMIN_EMAIL) == ADMIN_EMAIL

def test_reset_admin_password_is_importable_and_async():
    """The function must exist, be async, and accept (session, password=None)."""
    import asyncio
    import inspect

    assert inspect.iscoroutinefunction(reset_admin_password)
    params = inspect.signature(reset_admin_password).parameters
    assert "session" in params
    assert "password" in params


# ── 2. CLI command exists ────────────────────────────────────────────────────

def test_cli_reset_admin_password_is_registered():
    """e2eai-api reset-admin-password must appear in the CLI help."""
    from e2eai.manage import app

    result = runner.invoke(app, ["reset-admin-password", "--help"])
    assert result.exit_code == 0
    assert "creds-file" in result.output.lower()


# ── 3. --creds-file writes email + password, not the hash ───────────────────

def test_creds_file_written_by_cli(tmp_path):
    """When --creds-file is given, the command writes email\\npassword to that file."""
    from e2eai.manage import app

    creds_path = tmp_path / "admin_creds.txt"
    fake_password = gen_password()

    with patch("e2eai.manage._run_reset_admin", return_value=fake_password):
        result = runner.invoke(app, ["reset-admin-password", "--creds-file", str(creds_path)])

    assert result.exit_code == 0
    assert creds_path.exists()
    lines = creds_path.read_text().strip().splitlines()
    assert lines[0] == ADMIN_EMAIL
    assert lines[1] == fake_password


def test_creds_file_not_written_when_omitted():
    """Without --creds-file the password is printed to stdout, no file is created."""
    from e2eai.manage import app

    fake_password = gen_password()
    with patch("e2eai.manage._run_reset_admin", return_value=fake_password):
        result = runner.invoke(app, ["reset-admin-password"])

    assert result.exit_code == 0
    assert fake_password in result.output


# ── 4. Refuse a creds-file inside the repo tree ─────────────────────────────

def test_creds_file_inside_repo_is_rejected():
    """Writing credentials inside the repo directory must fail to prevent accidental commit."""
    from e2eai.manage import app

    repo_root = Path(__file__).resolve().parents[3]  # tests -> api -> apps -> repo root
    bad_path = repo_root / "scratch_admin_creds.txt"

    fake_password = gen_password()
    with patch("e2eai.manage._run_reset_admin", return_value=fake_password):
        result = runner.invoke(app, ["reset-admin-password", "--creds-file", str(bad_path)])

    assert result.exit_code != 0
    assert not bad_path.exists()
