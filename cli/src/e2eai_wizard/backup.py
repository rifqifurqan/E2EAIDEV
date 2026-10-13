"""Backup and restore planning (NFR-6): daily, open formats, restorable onto a fresh install.

Deterministic and secret-free, like `upgrade.py`: it emits operator commands that reference environment variables
(`$POSTGRES_USER`) and never read or embed `.env` values. The generated `.env` is copied only into a mode-600 file.
"""

from __future__ import annotations

from dataclasses import dataclass

# RPO limits in hours per profile (NFR-6); RTO is 4 h for a single node.
RPO_HOURS = {"single-node": 24, "ha": 1}
RTO_HOURS = {"single-node": 4}
POSTGRES_DBS = ("e2eai", "openfga", "litellm", "keycloak")


@dataclass(frozen=True)
class BackupTarget:
    name: str
    artifact: str
    open_format: bool
    description: str


BACKUP_TARGETS: tuple[BackupTarget, ...] = (
    BackupTarget("postgres", "postgres-<db>.dump", True,
                 "PostgreSQL custom-format dumps (pg_dump -Fc) for app, OpenFGA, LiteLLM and Keycloak databases."),
    BackupTarget("valkey", "valkey.tar.gz", True, "Valkey data volume (sessions, caches) as a tar archive."),
    BackupTarget("object-storage", "seaweedfs.tar.gz", True, "SeaweedFS (S3) data volume as a tar archive."),
    BackupTarget("config", "config.tar.gz", True, "e2eai.yaml, compose files and the secrets file (mode 600)."),
)

# FR-R3: only when Qdrant is the installed vector store (the pgvector rows are inside the Postgres dumps).
QDRANT_TARGET = BackupTarget("vector-store", "qdrant.tar.gz", True,
                             "Qdrant data volume (vectors; ids only, rebuildable from Postgres) as a tar archive.")
BACKUP_TARGETS_WITH_QDRANT: tuple[BackupTarget, ...] = (*BACKUP_TARGETS, QDRANT_TARGET)


@dataclass(frozen=True)
class BackupStep:
    phase: str
    title: str
    commands: list[str]
    notes: str = ""


@dataclass(frozen=True)
class BackupPlan:
    backup_dir: str
    steps: list[BackupStep]


def build_backup_plan(*, backup_dir: str = "backups/daily", compose_dir: str = "deploy/compose",
                      qdrant: bool = False) -> BackupPlan:
    dump_cmds = [
        f"cd {compose_dir} && docker compose exec -T postgres pg_dump -U \"$POSTGRES_USER\" -Fc {db} "
        f"> ../../{backup_dir}/postgres-{db}.dump"
        for db in POSTGRES_DBS
    ]
    data = BackupStep(
        phase="dump-data",
        title="Dump databases and archive volumes",
        commands=[
            f"mkdir -p {backup_dir}",
            *dump_cmds,
            f"docker run --rm -v e2eaidev_valkeydata:/data -v \"$PWD/{backup_dir}\":/backup alpine "
            "tar czf /backup/valkey.tar.gz /data",
            f"docker run --rm -v e2eaidev_swdata:/data -v \"$PWD/{backup_dir}\":/backup alpine "
            "tar czf /backup/seaweedfs.tar.gz /data",
            *([f"docker run --rm -v e2eaidev_qdrantdata:/data -v \"$PWD/{backup_dir}\":/backup alpine "
               "tar czf /backup/qdrant.tar.gz /data"] if qdrant else []),
        ],
        notes="Use the volume names shown by `docker volume ls`. Langfuse/ClickHouse traces are added when that profile is installed.",
    )
    config = BackupStep(
        phase="config",
        title="Save configuration (secrets file stays private)",
        commands=[
            f"cp {compose_dir}/.env {backup_dir}/env.private && chmod 600 {backup_dir}/env.private",
            f"tar czf {backup_dir}/config.tar.gz e2eai.yaml {compose_dir}/compose.yaml {compose_dir}/litellm",
        ],
        notes="`env.private` contains secrets: store it encrypted and never paste it into tickets or chat.",
    )
    verify = BackupStep(
        phase="verify",
        title="Record checksums and test the dumps are readable",
        commands=[
            f"cd {backup_dir} && sha256sum *.dump *.tar.gz > SHA256SUMS",
            f"cd {backup_dir} && for f in postgres-*.dump; do pg_restore --list \"$f\" > /dev/null || exit 1; done",
        ],
        notes="Run daily (cron or a scheduled task). Alert if the newest backup is older than the RPO.",
    )
    return BackupPlan(backup_dir=backup_dir, steps=[data, config, verify])


def build_restore_plan(*, backup_dir: str = "backups/daily", compose_dir: str = "deploy/compose",
                       api_dir: str = "apps/api", ready_url: str = "http://127.0.0.1:8000/api/v1/ready",
                       qdrant: bool = False) -> BackupPlan:
    prepare = BackupStep(
        phase="prepare",
        title="Prepare a fresh install and verify the backup",
        commands=[
            f"cd {backup_dir} && sha256sum -c SHA256SUMS",
            f"cp {backup_dir}/env.private {compose_dir}/.env && chmod 600 {compose_dir}/.env",
            f"cd {compose_dir} && docker compose up -d postgres valkey",
        ],
        notes="Restores onto a clean machine: install Docker, clone the repo, and run the wizard only if `.env` is missing.",
    )
    restore_cmds = [
        f"cd {compose_dir} && docker compose exec -T postgres pg_restore -U \"$POSTGRES_USER\" --clean --if-exists "
        f"-d {db} < ../../{backup_dir}/postgres-{db}.dump"
        for db in POSTGRES_DBS
    ]
    restore = BackupStep(
        phase="restore-data",
        title="Restore databases and volumes",
        commands=[
            *restore_cmds,
            f"docker run --rm -v e2eaidev_valkeydata:/data -v \"$PWD/{backup_dir}\":/backup alpine "
            "tar xzf /backup/valkey.tar.gz -C /",
            f"docker run --rm -v e2eaidev_swdata:/data -v \"$PWD/{backup_dir}\":/backup alpine "
            "tar xzf /backup/seaweedfs.tar.gz -C /",
            *([f"docker run --rm -v e2eaidev_qdrantdata:/data -v \"$PWD/{backup_dir}\":/backup alpine "
               "tar xzf /backup/qdrant.tar.gz -C /"] if qdrant else []),
        ],
        notes="Stop writers first. Restored state is exactly the backup time; changes after it are lost (RPO).",
    )
    migrate = BackupStep(
        phase="migrate",
        title="Bring the schema to the installed version",
        commands=[f"cd {api_dir} && uv run alembic upgrade head"],
        notes="Safe when the backup is from an older version; a no-op when it is current.",
    )
    health = BackupStep(
        phase="health-check",
        title="Start everything and check health",
        commands=[f"cd {compose_dir} && docker compose up -d", f"cd {compose_dir} && docker compose ps",
                  f"curl -fsS {ready_url}"],
        notes="Then run the permission leak suite before sending users back.",
    )
    return BackupPlan(backup_dir=backup_dir, steps=[prepare, restore, migrate, health])


def check_backup_age(*, age_hours: float, profile: str = "single-node") -> dict:
    """Compare the newest backup's age with the RPO of the profile (NFR-6)."""
    if profile not in RPO_HOURS:
        raise ValueError(f"unknown profile: {profile!r}")
    if age_hours < 0:
        raise ValueError("age_hours must not be negative")
    limit = RPO_HOURS[profile]
    ok = age_hours <= limit
    message = (f"Newest backup is {age_hours:g} h old, within the RPO of {limit} h." if ok else
               f"Newest backup is {age_hours:g} h old, which exceeds the RPO of {limit} h: run a backup now.")
    return {"ok": ok, "rpo_hours": limit, "age_hours": age_hours, "profile": profile, "message": message}


def render_backup_runbook(backup: BackupPlan, restore: BackupPlan, *, qdrant: bool = False) -> str:
    lines = [
        "# E2EAIDEV backup and restore",
        "",
        "Targets (NFR-6): **RPO <= 24 h** and **RTO <= 4 h** on a single node (RPO <= 1 h on the HA profile). "
        "Backups use open formats (PostgreSQL custom dumps, tar archives) so the company can always export and leave.",
        "",
        "Run the backup daily. Test a full restore onto a fresh install **quarterly** and record the result.",
        "",
        "## What is backed up",
        "",
    ]
    lines += [f"- **{t.name}**: {t.description}" for t in (BACKUP_TARGETS_WITH_QDRANT if qdrant else BACKUP_TARGETS)]
    for title, plan in (("Backup", backup), ("Restore onto a fresh install", restore)):
        lines += ["", f"# {title}"]
        for i, step in enumerate(plan.steps, 1):
            lines += ["", f"## {i}. {step.title}", "", f"Phase: `{step.phase}`", "", "```bash", *step.commands, "```"]
            if step.notes:
                lines += ["", step.notes]
    lines += ["", "## Verification", "",
              "- `sha256sum -c SHA256SUMS` passes before restoring.",
              "- `/api/v1/ready` returns success and the permission leak suite reports 0 leaks.",
              "- Record the backup date, restore duration (compare with the 4 h RTO) and the operator in the log."]
    return "\n".join(lines) + "\n"
