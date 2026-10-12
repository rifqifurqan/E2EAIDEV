# Upgrade Procedure Runbook (FR-F16)

This runbook prepares the P2 upgrade procedure for a Compose/Lite install: create a pre-upgrade backup, apply reversible Alembic migrations, run a health check, and roll back automatically if the upgraded service is not healthy.

## Symptoms

Use this runbook when:

- You are upgrading E2EAIDEV to a newer release.
- A migration failed during upgrade.
- `/api/v1/ready` fails after an upgrade.
- You need to restore the pre-upgrade state after an unsuccessful upgrade.

## Diagnosis

1. Confirm the current and target versions. FR-F16 allows patch upgrades and one-minor upgrades; do not skip more than one minor version.
2. Generate the operator procedure:

   ```bash
   cd cli
   uv run e2eai upgrade-plan \
     --from-version 0.1.0 \
     --to-version 0.1.1 \
     --backup-dir backups/pre-upgrade-YYYYMMDDHHMMSS \
     --previous-alembic-revision <previous_revision>
   ```

3. Confirm Docker Compose services are reachable:

   ```bash
   cd deploy/compose
   docker compose ps
   ```

4. Confirm the API is ready before starting:

   ```bash
   curl -fsS http://127.0.0.1:8000/api/v1/ready
   ```

## Fix

1. Create the pre-upgrade backup from the generated plan before pulling new code or running migrations. The plan includes Postgres, SeaweedFS, and Valkey backup commands.
2. Apply migrations:

   ```bash
   cd apps/api
   uv run alembic upgrade head
   ```

3. Run the post-upgrade health check:

   ```bash
   cd deploy/compose
   docker compose ps
   curl -fsS http://127.0.0.1:8000/api/v1/ready
   ```

4. If any migration or health check fails, run the rollback phase from the generated plan: downgrade to the previous Alembic revision, restore the pre-upgrade backup artifacts, and restart Compose services.

## Verification

- `docker compose ps` shows required services running/healthy.
- `/api/v1/ready` returns success.
- `cd apps/api && uv run alembic current` shows the intended head revision after success, or the previous revision after rollback.
- The operator log records the source version, target version, backup directory, migration result, health-check result, and rollback result if used.

## Notes

- Do not paste secrets into the generated plan, this runbook, or the operator log.
- Store backup artifacts outside the git repository for real installs.
- The generated plan uses environment variables inside the Compose container instead of exposing secret values in commands.
