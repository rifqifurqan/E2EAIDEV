"""Upgrade procedure planning helpers (FR-F16).

This module is deterministic and secret-free: it emits operator commands and
rollback notes without reading `.env` values or embedding credentials.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class UpgradeStep:
    phase: str
    title: str
    commands: list[str]
    notes: str = ""


@dataclass(frozen=True)
class UpgradePlan:
    from_version: str
    to_version: str
    backup_dir: str
    steps: list[UpgradeStep]


_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")


def _parse_version(version: str) -> tuple[int, int, int]:
    match = _VERSION_RE.match(version.strip())
    if not match:
        raise ValueError(f"unsupported semantic version: {version!r}")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def validate_upgrade_window(from_version: str, to_version: str) -> None:
    """Allow patch upgrades and one-minor upgrades; reject skipped minors (FR-F16)."""
    old_major, old_minor, old_patch = _parse_version(from_version)
    new_major, new_minor, new_patch = _parse_version(to_version)
    if (new_major, new_minor, new_patch) < (old_major, old_minor, old_patch):
        raise ValueError("downgrades are rollback operations, not upgrades")
    if new_major != old_major:
        raise ValueError("upgrades must skip at most one minor version")
    if new_minor - old_minor > 1:
        raise ValueError("upgrades must skip at most one minor version")


def build_upgrade_plan(
    *,
    from_version: str,
    to_version: str,
    backup_dir: str = "backups/pre-upgrade",
    compose_dir: str = "deploy/compose",
    api_dir: str = "apps/api",
    ready_url: str = "http://127.0.0.1:8000/api/v1/ready",
    previous_alembic_revision: str = "base",
) -> UpgradePlan:
    """Build the Lite/Compose upgrade procedure: backup -> migrate -> health -> rollback."""
    validate_upgrade_window(from_version, to_version)
    backup = UpgradeStep(
        phase="pre-upgrade-backup",
        title="Create pre-upgrade backup",
        commands=[
            f"mkdir -p {backup_dir}",
            f"cd {compose_dir} && docker compose exec -T postgres pg_dump -U \"$POSTGRES_USER\" -Fc e2eai > ../../{backup_dir}/postgres.dump",
            f"docker run --rm -v e2eaidev_seaweeddata:/data -v \"$PWD/{backup_dir}\":/backup alpine tar czf /backup/seaweedfs.tar.gz /data",
            f"docker run --rm -v e2eaidev_valkeydata:/data -v \"$PWD/{backup_dir}\":/backup alpine tar czf /backup/valkey.tar.gz /data",
        ],
        notes="Run before pulling new code or applying migrations. Store artifacts outside the repo if possible.",
    )
    migrate = UpgradeStep(
        phase="migrate",
        title="Apply database migrations",
        commands=[f"cd {api_dir} && uv run alembic upgrade head"],
        notes="Alembic migrations are reversible from the first schema; stop on any failure.",
    )
    health = UpgradeStep(
        phase="health-check",
        title="Run post-upgrade health check",
        commands=[
            f"cd {compose_dir} && docker compose ps",
            f"curl -fsS {ready_url}",
        ],
        notes="The ready endpoint must return 2xx before users are sent back to the upgraded service.",
    )
    rollback = UpgradeStep(
        phase="rollback",
        title="Rollback if migration or health check fails",
        commands=[
            f"cd {api_dir} && uv run alembic downgrade {previous_alembic_revision}",
            f"cd {compose_dir} && docker compose down",
            f"# Restore Postgres from {backup_dir}/postgres.dump with pg_restore into a clean e2eai database",
            f"# Restore SeaweedFS and Valkey volumes from {backup_dir}/seaweedfs.tar.gz and {backup_dir}/valkey.tar.gz",
            f"cd {compose_dir} && docker compose up -d",
        ],
        notes="Prefer automatic rollback when health fails: downgrade schema, restore backup artifacts, then restart services.",
    )
    return UpgradePlan(from_version=from_version, to_version=to_version, backup_dir=backup_dir, steps=[backup, migrate, health, rollback])


def render_upgrade_runbook(plan: UpgradePlan) -> str:
    """Render an operator-facing Markdown procedure without secrets."""
    lines = [
        "# E2EAIDEV upgrade procedure",
        "",
        f"From `{plan.from_version}` to `{plan.to_version}`.",
        "",
        "Run these phases in order. Stop immediately on any failed command.",
    ]
    for i, step in enumerate(plan.steps, 1):
        lines += ["", f"## {i}. {step.title}", "", f"Phase: `{step.phase}`", "", "```bash"]
        lines.extend(step.commands)
        lines += ["```"]
        if step.notes:
            lines += ["", step.notes]
    lines += [
        "",
        "## Verification",
        "",
        "- Confirm compose services are healthy.",
        "- Confirm `/api/v1/ready` returns success.",
        "- Record the backup directory and target version in the operator log.",
    ]
    return "\n".join(lines) + "\n"
