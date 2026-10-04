# AGENTS.md — E2EAIDEV

Read [E2EAIDEV_PRD.md](E2EAIDEV_PRD.md) (Part I requirements, §17 build contract, Part II technical design) first, then this file.

## Setup
1. Docker Desktop running; Python 3.12 available; `uv` installed.
2. `cd cli && uv run e2eai`: the wizard detects the machine, picks free ports, asks usernames/passwords, and writes `deploy/compose/.env` (secrets, gitignored), `deploy/compose/seaweedfs/s3.json` (gitignored), and `e2eai.yaml`.
3. `cd deploy/compose && docker compose up -d && docker compose ps`.

## Conventions
- Images are pinned by digest in `deploy/versions.lock`; the wizard copies them into `.env`. Never use floating tags.
- Secrets live only in `deploy/compose/.env`; `e2eai.yaml` references them as `env:NAME`.
- Secrets use only `[A-Za-z0-9._~-]`, ≥ 16 chars, so they are safe in DSNs, `.env`, and SQL without escaping.
- Shell scripts used inside containers must keep LF line endings (`.gitattributes`).

## Progress
- **Phase 0, in progress.** Done: CLI wizard for infrastructure (FR-F5 hardware/tier/services/ports/credentials, FR-F19 tier, FR-F21 config file), pinned Lite compose stack (postgres+pgvector, valkey, openfga, seaweedfs, litellm; optional ollama, TEI, keycloak). Tests: `cli/tests` 18 passed.
- **Not yet:** model selection step (FR-F5a/F5b), Caddy (needs the app), Langfuse/Temporal profiles, api/worker/web apps, `verify-phase-0`.
- **Smoke test passed 2026-10-05 on the owner's PC (Lite, host Ollama):** postgres (openfga/litellm/keycloak DBs + pgvector 0.8.7), valkey (rejects wrong password), openfga (200 with key, 401 without), seaweedfs S3 (read/write with keys, `InvalidAccessKeyId` without), litellm (alive, 200 with master key, 401 without, reaches host Ollama 0.16.3). Stack RAM: 0.87 GiB (target ≤ 6 GiB). Docker VM limit is 4.8 GiB: raise the WSL memory limit before adding the worker (Docling ≈ 2 GB).
- **Next 3 tasks:** (1) model selection step in the wizard (FR-F5a/F5b), registering chosen models in LiteLLM; (2) app skeleton (`apps/api` core + Alembic baseline); (3) OpenFGA model file + model tests.

## Decisions (newest first)
- **2026-10-05 · Valkey instead of Redis.** Context: Redis 8 is licensed AGPLv3/RSALv2/SSPLv1. Decision: Valkey 9.1 (BSD-3, Linux Foundation), a drop-in replacement (same protocol, works with Celery/redis-py). Alternative: Redis 8 under AGPL as a separate service.
- **2026-10-05 · Default host ports in the 1xxxx range** (15432, 16379, 18080, 18333, 14000, 21434, 18081/18082, 18180) and bound to 127.0.0.1. Context: the owner's PC already uses 5432, 6379, 3000, 11434. The wizard skips busy ports automatically.
- **2026-10-05 · Reuse a host Ollama when detected.** The wizard offers the Ollama already running on the machine (LiteLLM reaches it at `host.docker.internal:11434`) instead of starting a second one.
- **2026-10-05 · Wizard dependencies kept minimal:** Typer (includes Rich) and PyYAML; hardware detection uses the standard library (no psutil).
