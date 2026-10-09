# E2EAIDEV Admin & Operator Guide

This guide covers installation, configuration, day-to-day operations, and maintenance for platform administrators.

---

## Installation

### Prerequisites

| Component | Minimum |
|-----------|---------|
| OS | Linux (Ubuntu 22.04+), Windows 11 with WSL2, macOS 13+ |
| Docker | Docker Desktop or Docker Engine 24+ with Compose v2 |
| Python | 3.12 (managed via uv; do not modify the system Python) |
| Node.js | 20+ (for the web frontend) |
| RAM | Lite: 8 GB, Standard: 16 GB, Enterprise: 32 GB+ |
| Disk | 20 GB minimum for images + models |

### Install Tiers

| Tier | Description | Components |
|------|-------------|------------|
| **Lite** | Single-machine, minimal resources | Postgres+pgvector, Valkey, OpenFGA, SeaweedFS, LiteLLM, Ollama (host) |
| **Standard** | Full lab with GPU serving | All Lite + vLLM, TEI, Langfuse, Temporal |
| **Enterprise** | Multi-node, HA, SCIM | All Standard + clustering, SCIM sync, advanced audit |

### Step-by-Step Installation

1. **Clone the repository:**

        git clone https://github.com/rifqifurqan/E2EAIDEV.git
        cd E2EAIDEV

2. **Run the install wizard:**

        cd cli && uv run e2eai

   The wizard will:
   - Detect your hardware (CPU, RAM, GPU/VRAM, disk)
   - Recommend a tier (Lite/Standard/Enterprise)
   - Let you choose models for each role (chat, embedding, reranker, judge, safety)
   - Choose the job engine (Celery default, or Temporal for Standard+)
   - Generate deploy/compose/.env (secrets, gitignored) and e2eai.yaml (config)
   - Pull pinned container images

   Use --yes to accept defaults, --force to overwrite an existing .env (a backup is kept).

3. **Start the infrastructure:**

        cd deploy/compose && docker compose up -d

4. **Verify services are running:**

        docker compose ps

   Expected: postgres, valkey, openfga, seaweedfs, litellm all show running or healthy.

5. **Run database migrations:**

        cd apps/api && uv run alembic upgrade head

6. **Bootstrap the admin account:**

        cd apps/api && uv run e2eai-api bootstrap-admin

   This creates the break-glass admin. The password is displayed **once** -- store it securely.

7. **Bootstrap the authorization model:**

        cd apps/api && uv run e2eai-api bootstrap-authz

8. **Seed demo data (optional):**

        cd apps/api && uv run e2eai-api seed-demo

   Creates a demo organization with sample users (Andi/Sales, Budi/HR, Intern).

9. **Verify the full Phase 0 stack:**

        cd apps/api && uv run e2eai-api verify-phase-0

   This runs compose health checks, CLI tests, API tests, Alembic migrations, API health/ready
   endpoints, LiteLLM chat and embedding, and the OpenFGA authorization model check.

### Wizard Tests

    cd cli && uv run pytest -q

### API Tests

    cd apps/api && uv run pytest -q

---

## Configuration

### Configuration File (e2eai.yaml)

The wizard generates e2eai.yaml at the repository root. This file captures the entire
installation: tier, components, models, and policies. It can be versioned in git, diffed,
and re-applied.

- Secrets are **referenced** (e.g., env:POSTGRES_PASSWORD), never stored in the config file.
- Invalid configuration fails at startup with a clear error message.
- Validate config:

        cd apps/api && uv run e2eai-api check-config

### Environment Variables (deploy/compose/.env)

All secrets live in deploy/compose/.env, which is gitignored. The wizard generates this file.
Key variables include database credentials, Valkey auth, OpenFGA preshared key, LiteLLM master
key, and SeaweedFS S3 keys.

All generated secrets use [A-Za-z0-9._~-], at least 16 characters, safe for DSNs and .env
without escaping.

### Port Configuration

Default host ports are in the 1xxxx range, bound to 127.0.0.1:

| Service | Default Port |
|---------|-------------|
| Postgres | 15432 |
| Valkey | 16379 |
| OpenFGA | 18080 |
| SeaweedFS | 18333 |
| LiteLLM | 14000 |
| Ollama (host) | 11434 |
| Keycloak | 18081 / 18082 |

The wizard skips busy ports automatically. Ports can be changed in .env.

### Model Configuration

Models are chosen during wizard setup. Each role (chat, embedding, reranker, judge, safety)
can have one or more models configured. To change models later:

1. Edit e2eai.yaml under the models section.
2. Register or update models in LiteLLM via its admin API or config.
3. Verify:

        cd apps/api && uv run e2eai-api verify-phase-0

### Data Egress Policy

External model APIs are **off by default**. To enable:

1. Set the admin-level egress setting in the configuration.
2. Per sensitivity label, choose allowed destinations (e.g., Confidential/Restricted content
   goes only to local models).
3. The LiteLLM gateway enforces the policy; blocked calls are audited.

---

## Backup

### Database Backup

    # Backup Postgres (run from the host)
    docker compose -f deploy/compose/compose.yaml exec postgres \
      pg_dump -U "$POSTGRES_USER" e2eai > backup.sql

    # Backup with compression
    docker compose -f deploy/compose/compose.yaml exec postgres \
      pg_dump -U "$POSTGRES_USER" -Fc e2eai > backup.dump

### Object Storage Backup

SeaweedFS data is stored in Docker volumes. Back up the volume:

    docker volume ls | grep seaweed
    docker run --rm -v e2eaidev_seaweeddata:/data -v "$PWD":/backup alpine \
      tar czf /backup/seaweedfs_backup.tar.gz /data

### Valkey Backup

    docker run --rm -v e2eaidev_valkeydata:/data -v "$PWD":/backup alpine \
      tar czf /backup/valkey_backup.tar.gz /data

### Restore

See [Runbook: Restore from Backup](../runbooks/restore-from-backup.md).

---

## Monitoring

### Health Endpoints

| Endpoint | Purpose |
|----------|---------|
| GET /api/v1/health | Application liveness (returns status ok) |
| GET /api/v1/ready | Application readiness (checks database connectivity) |

### Docker Compose Health

    cd deploy/compose && docker compose ps

All services should show running or healthy. If any service shows unhealthy or restarting,
check logs:

    docker compose logs <service-name> --tail=50

### Key Metrics to Watch

- **Postgres**: connections, replication lag, disk usage
- **Valkey**: memory usage, connected clients, evictions
- **LiteLLM**: request latency, error rate, token usage
- **SeaweedFS**: storage utilization, read/write latency
- **OpenFGA**: authorization check latency

### Audit Log

Every login, upload, share, permission change, query, tool call, release, and admin action is
recorded in the audit log. The log is tamper-evident. Audit events are stored in the
audit_events table in Postgres.

---

## User Management

### Organization Model

The platform uses a hierarchical model: **Organization > Division > Team > User**, with roles.

### Creating Users

Users are provisioned through:

1. **SSO/OIDC** (Keycloak): users are created on first login.
2. **Seed command**: cd apps/api && uv run e2eai-api seed-demo (demo data).
3. **API**: POST /api/v1/auth/register (if local registration is enabled).

### Roles

| Role | Permissions |
|------|-------------|
| Admin | Full platform access, user management, configuration |
| AI Engineer | Model configuration, evaluation, bot management |
| Evaluator | Review answers, label datasets |
| Compliance | Audit log access, risk classification |
| Business User | Document upload, sharing, chat |

### User Offboarding

When an employee leaves the organization:

**Via CLI:**

    cd apps/api && uv run e2eai-api deactivate-user <target_email> <transfer_to_email> <admin_email>

**Via API:**

    curl -X POST http://localhost:18000/api/v1/users/<user-id>/deactivate \
      -H "Authorization: Bearer <admin-token>" \
      -H "Content-Type: application/json" \
      -d '{"transfer_to_id": "<manager-user-id>"}'

The offboarding process:

1. Sets the user status to **disabled** -- login and sessions stop immediately.
2. Revokes all active Valkey sessions (within 1 minute).
3. Transfers owned documents and folders to the designated recipient.
4. Existing shares to other users remain intact.
5. Chat history is retained but inaccessible to the disabled user.
6. All actions are audited.

---

## Evaluation Lab

### Creating Eval Datasets

Supports deterministic synthetic Q&A, adversarial, and persona-based test generation from
source chunks. Use the POST /api/v1/evals/datasets endpoint.

### Running Evaluations

Use POST /api/v1/evals/runs with a dataset ID and adapter (e.g., local_ragas). Results include
normalized metrics, item-level results, and regression comparison between runs.

### Permission-Leak Suite

The built-in permission-leak test suite verifies that restricted documents never appear in
unauthorized retrieval results. A leak failure blocks the release.

---

## Bot Management

### Creating and Releasing Bots

Bots are containers for versioned AI configurations. Each release creates an immutable bundle.
Rollback switches the production pointer to a previous bundle.

### Prompt Registry

Prompts are managed as immutable versions before they are referenced from bot bundles. Use the
prompt registry API to create a prompt, add a new version, move the `staging` or `production`
label to a version, compare two versions with a unified diff, and render a local playground
preview with `{{ variable }}` placeholders. The playground preview is offline and does not call
an LLM; it rejects missing or unsafe placeholders.

### Bot Access and Scope

- Grant access to users, teams, roles, or divisions.
- Set a knowledge scope (selected folders/documents).
- Effective retrieval = bot scope intersected with the user permissions.

---

## Runbooks

See the [runbooks directory](../runbooks/) for incident response:

- [Service Down](../runbooks/service-down.md)
- [Restore from Backup](../runbooks/restore-from-backup.md)
- [Model Endpoint Failing](../runbooks/model-endpoint-failing.md)
- [Vector Store Degraded](../runbooks/vector-store-degraded.md)
- [Permission Sync Lag](../runbooks/permission-sync-lag.md)
- [Disk Full](../runbooks/disk-full.md)
- [Leaked Key](../runbooks/leaked-key.md)

---

## Useful Commands Reference

| Task | Command |
|------|---------|
| Run install wizard | cd cli && uv run e2eai |
| Start infrastructure | cd deploy/compose && docker compose up -d |
| Check service status | cd deploy/compose && docker compose ps |
| View service logs | docker compose logs service --tail=50 |
| Run database migrations | cd apps/api && uv run alembic upgrade head |
| Bootstrap admin account | cd apps/api && uv run e2eai-api bootstrap-admin |
| Bootstrap authorization | cd apps/api && uv run e2eai-api bootstrap-authz |
| Seed demo data | cd apps/api && uv run e2eai-api seed-demo |
| Validate config | cd apps/api && uv run e2eai-api check-config |
| Verify Phase 0 | cd apps/api && uv run e2eai-api verify-phase-0 |
| Run CLI tests | cd cli && uv run pytest -q |
| Run API tests | cd apps/api && uv run pytest -q |
| Deactivate user | cd apps/api && uv run e2eai-api deactivate-user target transfer admin |
| Index a document | cd apps/api && uv run e2eai-api index-document doc-uuid |
| Trash a document | cd apps/api && uv run e2eai-api trash-document doc-uuid actor-email |
| Restore from trash | cd apps/api && uv run e2eai-api restore-document doc-uuid actor-email |
| Purge a document | cd apps/api && uv run e2eai-api purge-document doc-uuid actor-email |
| Ingest a doc version | cd apps/api && uv run e2eai-api ingest-version version-uuid |
| Validate docs | python scripts/validate_docs.py |
