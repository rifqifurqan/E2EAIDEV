# Runbook: Disk Full

## Symptoms

- Docker containers fail to start or crash with write errors.
- Postgres logs show "No space left on device".
- File uploads fail.
- docker system df shows high disk usage.

## Diagnosis

1. Check host disk usage:

        df -h

2. Check Docker disk usage:

        docker system df

3. Check individual volume sizes:

        docker system df -v | head -40

4. Check Postgres database size:

        docker compose -f deploy/compose/compose.yaml exec postgres \
          psql -U "$POSTGRES_USER" -d e2eai -c "SELECT pg_size_pretty(pg_database_size('e2eai'));"

5. Identify largest tables:

        docker compose -f deploy/compose/compose.yaml exec postgres \
          psql -U "$POSTGRES_USER" -d e2eai \
          -c "SELECT tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) \
              FROM pg_tables WHERE schemaname='public' ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC LIMIT 10;"

## Fix

1. **Clean up Docker:**

        # Remove unused images, containers, and build cache
        docker system prune -f

        # Remove dangling volumes (be careful -- this removes ALL unused volumes)
        docker volume prune -f

2. **Clean up Postgres:**
   - Vacuum to reclaim space:

            docker compose exec postgres psql -U "$POSTGRES_USER" -d e2eai \
              -c "VACUUM FULL;"

   - Purge trashed documents past retention:

            cd apps/api && uv run e2eai-api purge-document <doc-uuid> <admin-email>

3. **Clean up old model files (Ollama):**

        ollama list
        ollama rm <unused-model>

4. **Clean up old backups:**

        ls -lt backup*.sql backup*.dump
        # Remove old backups after confirming a recent one exists

5. **Expand disk (if possible):** increase the Docker volume size or move Docker data
   to a larger disk.

## Verification

1. Confirm disk space recovered:

        df -h
        docker system df

2. Restart any services that crashed:

        cd deploy/compose && docker compose up -d

3. Verify system health:

        cd apps/api && uv run e2eai-api verify-phase-0

## Escalation

- If disk is consistently full, plan for capacity expansion.
- Consider setting up monitoring alerts for disk usage above 80%.
- Review data retention policies and automate old backup cleanup.
