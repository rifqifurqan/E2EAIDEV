# Runbook: Restore from Backup

## Symptoms

- Data loss detected (missing documents, corrupted database, accidental deletion).
- Database migration failed and rolled back.
- Disaster recovery scenario.

## Diagnosis

1. Confirm the scope of data loss:

        cd apps/api && uv run e2eai-api verify-phase-0

2. List available backups:

        ls -lt backup*.sql backup*.dump 2>/dev/null

3. Check database state:

        docker compose -f deploy/compose/compose.yaml exec postgres \
          psql -U "$POSTGRES_USER" -d e2eai -c "SELECT count(*) FROM documents;"

## Fix

### Restoring the Postgres Database

1. **Stop the API to prevent writes:**

        # Stop the API process (if running natively)
        # or remove the API from compose

2. **Drop and recreate the database:**

        docker compose -f deploy/compose/compose.yaml exec postgres \
          psql -U "$POSTGRES_USER" -c "DROP DATABASE IF EXISTS e2eai;"
        docker compose -f deploy/compose/compose.yaml exec postgres \
          psql -U "$POSTGRES_USER" -c "CREATE DATABASE e2eai;"

3. **Restore from the SQL backup:**

        cat backup.sql | docker compose -f deploy/compose/compose.yaml exec -T postgres \
          psql -U "$POSTGRES_USER" -d e2eai

   Or from a compressed backup:

        docker compose -f deploy/compose/compose.yaml exec -T postgres \
          pg_restore -U "$POSTGRES_USER" -d e2eai < backup.dump

4. **Re-run migrations to ensure schema is current:**

        cd apps/api && uv run alembic upgrade head

### Restoring SeaweedFS

1. Stop seaweedfs:

        docker compose stop seaweedfs

2. Restore the volume from backup:

        docker run --rm -v e2eaidev_seaweeddata:/data -v "$PWD":/backup alpine \
          sh -c "rm -rf /data/* && tar xzf /backup/seaweedfs_backup.tar.gz -C /"

3. Restart:

        docker compose up -d seaweedfs

### Restoring Valkey

1. Stop valkey:

        docker compose stop valkey

2. Restore:

        docker run --rm -v e2eaidev_valkeydata:/data -v "$PWD":/backup alpine \
          sh -c "rm -rf /data/* && tar xzf /backup/valkey_backup.tar.gz -C /"

3. Restart:

        docker compose up -d valkey

## Verification

1. Run the full verification suite:

        cd apps/api && uv run e2eai-api verify-phase-0

2. Check document counts and data integrity:

        docker compose -f deploy/compose/compose.yaml exec postgres \
          psql -U "$POSTGRES_USER" -d e2eai -c "SELECT count(*) FROM documents;"

3. Test a sample chat query to confirm retrieval works.

## Escalation

- If the backup is corrupted or too old, contact the platform owner.
- Document the timeline and scope of data loss for the incident report.
- Consider implementing automated daily backups if not already in place.
