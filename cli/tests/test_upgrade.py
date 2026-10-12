"""FR-F16 upgrade procedure P2 prep: backup -> migrate -> health check -> rollback."""

import pytest
from typer.testing import CliRunner

from e2eai_wizard.cli import app
from e2eai_wizard.upgrade import (
    build_upgrade_plan,
    render_upgrade_runbook,
    validate_upgrade_window,
)


def test_upgrade_plan_requires_backup_migration_health_and_rollback_steps():
    plan = build_upgrade_plan(
        from_version="0.1.0",
        to_version="0.1.1",
        backup_dir="backups/2026-10-12T153000Z",
        compose_dir="deploy/compose",
        api_dir="apps/api",
        ready_url="http://127.0.0.1:8000/api/v1/ready",
        previous_alembic_revision="0019_system_registrations",
    )

    assert [step.phase for step in plan.steps] == [
        "pre-upgrade-backup",
        "migrate",
        "health-check",
        "rollback",
    ]
    backup_commands = "\n".join(plan.steps[0].commands)
    assert "pg_dump" in backup_commands
    assert "seaweedfs" in backup_commands
    assert "valkey" in backup_commands
    assert plan.steps[1].commands == ["cd apps/api && uv run alembic upgrade head"]
    assert "curl -fsS http://127.0.0.1:8000/api/v1/ready" in plan.steps[2].commands
    assert "uv run alembic downgrade 0019_system_registrations" in "\n".join(plan.steps[3].commands)
    assert "restore" in plan.steps[3].notes.lower()


def test_upgrade_window_allows_same_or_next_minor_only():
    validate_upgrade_window("1.2.0", "1.2.4")
    validate_upgrade_window("1.2.0", "1.3.0")

    with pytest.raises(ValueError, match="skip at most one minor"):
        validate_upgrade_window("1.2.0", "1.4.0")

    with pytest.raises(ValueError, match="downgrades are rollback"):
        validate_upgrade_window("1.3.0", "1.2.9")


def test_upgrade_runbook_rendering_is_secret_free_and_operator_ready():
    plan = build_upgrade_plan(
        from_version="0.1.0",
        to_version="0.1.1",
        backup_dir="backups/upgrade-demo",
        previous_alembic_revision="0019_system_registrations",
    )

    text = render_upgrade_runbook(plan)

    assert "# E2EAIDEV upgrade procedure" in text
    assert "pre-upgrade backup" in text.lower()
    assert "health check" in text.lower()
    assert "rollback" in text.lower()
    assert "env:" not in text.lower()
    assert "password" not in text.lower()
    assert "token" not in text.lower()


def test_upgrade_plan_cli_renders_operator_procedure():
    result = CliRunner().invoke(
        app,
        [
            "upgrade-plan",
            "--from-version", "0.1.0",
            "--to-version", "0.1.1",
            "--backup-dir", "backups/upgrade-demo",
            "--previous-alembic-revision", "0019_system_registrations",
        ],
    )

    assert result.exit_code == 0
    assert "E2EAIDEV upgrade procedure" in result.output
    assert "pg_dump" in result.output
    assert "alembic upgrade head" in result.output
    assert "alembic downgrade 0019_system_registrations" in result.output
