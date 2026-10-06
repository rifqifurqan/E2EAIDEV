# Runbook: Service Down

## Symptoms

- docker compose ps shows one or more services as "exited", "unhealthy", or "restarting".
- API returns 503 or connection refused.
- Health endpoint GET /api/v1/health or GET /api/v1/ready fails.

## Diagnosis

1. Check which services are down:

        cd deploy/compose && docker compose ps

2. Check logs for the failing service:

        docker compose logs <service-name> --tail=100

3. Check system resources:

        docker stats --no-stream
        df -h

4. Check if ports are in use by another process:

        netstat -tlnp | grep <port>

## Fix

1. **Restart the failing service:**

        docker compose restart <service-name>

2. **If the service fails to start, check for resource issues:**
   - Out of memory: increase Docker memory limit in .wslconfig (Windows) or daemon.json (Linux).
   - Port conflict: stop the conflicting process or change the port in .env.
   - Disk full: see the [Disk Full runbook](disk-full.md).

3. **If the service depends on another (e.g., openfga depends on postgres):**

        docker compose up -d

   This restarts services in dependency order.

4. **For a full stack restart:**

        docker compose down && docker compose up -d

## Verification

1. Confirm all services are healthy:

        docker compose ps

2. Check application health:

        curl http://127.0.0.1:18000/api/v1/health
        curl http://127.0.0.1:18000/api/v1/ready

3. Run the Phase 0 verification:

        cd apps/api && uv run e2eai-api verify-phase-0

## Escalation

- If a service repeatedly crashes, check for data corruption in its volume.
- If postgres fails to start, check WAL corruption and consider restoring from backup.
- Collect logs and resource metrics before escalating to the platform owner.
