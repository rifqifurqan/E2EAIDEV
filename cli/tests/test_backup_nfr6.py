"""NFR-6: daily backups in open formats, restore onto a fresh install, RPO/RTO check. Secret-free plans."""

import pytest
from typer.testing import CliRunner

from e2eai_wizard.backup import (
    BACKUP_TARGETS,
    build_backup_plan,
    build_restore_plan,
    check_backup_age,
    render_backup_runbook,
)
from e2eai_wizard.cli import app


def _cmds(plan):
    return [c for step in plan.steps for c in step.commands]


def test_backup_covers_every_store_in_open_formats():
    plan = build_backup_plan(backup_dir="backups/2026-10-13")
    text = "\n".join(_cmds(plan))
    dumps = [c for c in _cmds(plan) if "pg_dump" in c]
    assert len(dumps) == 4 and all(" -Fc " in c for c in dumps)  # custom (open) format, one per database
    for db in ("e2eai", "openfga", "litellm", "keycloak"):
        assert any(f"-Fc {db} " in c and f"postgres-{db}.dump" in c for c in dumps), db
    assert "valkey" in text.lower() and "seaweedfs" in text.lower()
    assert "e2eai.yaml" in text
    assert {t.name for t in BACKUP_TARGETS} >= {"postgres", "valkey", "object-storage", "config"}
    assert all(t.open_format for t in BACKUP_TARGETS)


def test_backup_plan_embeds_no_secret_values_only_env_references():
    plan = build_backup_plan(backup_dir="backups/x")
    text = "\n".join(_cmds(plan))
    assert "$POSTGRES_USER" in text or "${POSTGRES_USER}" in text
    assert "PGPASSWORD" not in text and "password=" not in text.lower()
    # .env holds secrets: it is copied only to a mode-600 file, never printed
    assert "chmod 600" in text


def test_backup_plan_verifies_artifacts_with_checksums():
    plan = build_backup_plan(backup_dir="backups/x")
    assert any("sha256sum" in c for c in _cmds(plan))
    assert [s.phase for s in plan.steps][-1] == "verify"


def test_restore_plan_targets_a_fresh_install_and_checks_health():
    plan = build_restore_plan(backup_dir="backups/x")
    phases = [s.phase for s in plan.steps]
    assert phases == ["prepare", "restore-data", "migrate", "health-check"]
    text = "\n".join(_cmds(plan))
    assert "pg_restore" in text and "alembic upgrade head" in text and "/api/v1/ready" in text
    assert "sha256sum -c" in text  # checksums verified before restoring


@pytest.mark.parametrize("profile,limit_h", [("single-node", 24), ("ha", 1)])
def test_rpo_limit_depends_on_profile(profile, limit_h):
    ok = check_backup_age(age_hours=limit_h - 0.1, profile=profile)
    bad = check_backup_age(age_hours=limit_h + 0.1, profile=profile)
    assert ok["ok"] is True and ok["rpo_hours"] == limit_h
    assert bad["ok"] is False and "RPO" in bad["message"]


def test_rpo_check_rejects_unknown_profile_and_negative_age():
    with pytest.raises(ValueError):
        check_backup_age(age_hours=1, profile="mystery")
    with pytest.raises(ValueError):
        check_backup_age(age_hours=-1, profile="ha")


def test_runbook_states_rpo_rto_and_quarterly_restore_test():
    text = render_backup_runbook(build_backup_plan(backup_dir="backups/x"), build_restore_plan(backup_dir="backups/x"))
    assert "RPO" in text and "24" in text and "RTO" in text and "4" in text
    assert "quarterly" in text.lower()


def test_backup_plan_cli_prints_runbook_without_secrets():
    r = CliRunner().invoke(app, ["backup-plan", "--backup-dir", "backups/2026-10-13"])
    assert r.exit_code == 0, r.output
    assert 'pg_dump -U "$POSTGRES_USER" -Fc e2eai' in r.output and "pg_restore" in r.output
    assert "backups/2026-10-13" in r.output
