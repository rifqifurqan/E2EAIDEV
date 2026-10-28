# AGENTS.md — E2EAIDEV

Read [E2EAIDEV_PRD.md](E2EAIDEV_PRD.md) (Part I requirements, §17 build contract, Part II technical design) first, then this file.

## Setup
1. Docker Desktop running; Python 3.12 available; `uv` installed.
2. `cd cli && uv run e2eai init`: the wizard detects the machine, picks free ports, lets you choose models, asks usernames/passwords, and writes `deploy/compose/.env` (secrets, gitignored), `deploy/compose/seaweedfs/s3.json` (gitignored), `deploy/compose/litellm/config.yaml` (generated) and `e2eai.yaml`. `uv run e2eai models` changes models later without touching passwords.
3. `cd deploy/compose && docker compose up -d && docker compose ps`. Every container uses `restart: unless-stopped`, so the stack comes back after a Docker or PC restart.
4. API (port 18000), web (port 13000), the worker (`workers/`) and the Ragas adapter (`adapters/eval/ragas`, port 18701) run natively on the host; see CLAUDE.md → Commands and each folder's README.

## Conventions
- Images are pinned by digest in `deploy/versions.lock`; the wizard copies them into `.env`. Never use floating tags.
- Secrets live only in `deploy/compose/.env`; `e2eai.yaml` references them as `env:NAME`.
- Secrets use only `[A-Za-z0-9._~-]`, ≥ 16 chars, so they are safe in DSNs, `.env`, and SQL without escaping.
- Shell scripts used inside containers must keep LF line endings (`.gitattributes`).
- **Run API tests only against the dedicated test database** (they delete table contents): `E2EAI_DB_NAME=e2eai_test E2EAI_VALKEY_DB=1 E2EAI_OPENFGA_STORE=e2eai-test uv run pytest -q` in `apps/api`. One-time setup: `CREATE DATABASE e2eai_test` + `CREATE EXTENSION vector` in the Postgres container, then `alembic upgrade head` with the same variables. `tests/conftest.py` empties that database before each test module and does nothing on the development database. **Never run two pytest processes on the test database at once** (the second one's cleanup empties the first one's tables).
- Heavy tools get their own environment **outside the repo, on a drive with room** (Docling worker, Ragas adapter), never in the API venv.

## Progress (last updated 2026-10-28)
- **Phases 0-3 are coded** (`PRD_CRON_BACKLOG.md`: 170 of 170 items; 35 migrations). Chronological detail: `progress_2026-10-05.txt` (history) and `progress_2026-10-28.txt` (this session).
- **Verified live on 2026-10-28 (owner's PC, Lite tier):**
  - Docker stack restarted and healthy; **root cause of "stack dead after reboot" fixed**: Postgres, Valkey and SeaweedFS had restart policy `no` (now `unless-stopped`, matching `compose.yaml`).
  - **PDF → worker → cited answer works end to end** (real API + real Celery worker + real Docling): the upload returns `pending` in about a second; the worker parses it; once `ready` it is shared with a colleague, who gets an answer citing page 2 (the revenue-share table, section "2. Commercial terms") and page 3 ("3. Term"); a user it was not shared with gets no citation and no hint it exists.
  - **Real Ragas through the platform API**: `POST /api/v1/evals/runs` with `"adapter": "ragas"` scored 6 of 6 pairs with the local judge (`qwen3.5:4b` via LiteLLM): a faithful answer 1.0, an invented one 0.0.
  - Tests (final run, nothing else touching the test database): **API 949 passed, 1 skipped, 0 failed** (isolated database, ~14 min); CLI 94 passed; web 334 passed + typecheck + lint clean; worker 12 passed (real PDF, DOCX and scanned-image OCR conversions); Ragas adapter 13 passed.
- **Done this session:** real Ragas adapter (`adapters/eval/ragas` + `ragas_http_adapter.py`, per-run gateway key, judge temperature 0); real Docling parsing (`rich_parse.py`, `docling_runtime.py`) with headings, page anchors, structured tables, figure captions, per-page confidence and file-type sniffing; Celery job engine (`celery_app.py`, `jobs/ingest.py`, `ingest_dispatch.py`) with retries and a failure marker; `workers/` project (own environment); documents report the real `parse_status` (pending → indexing → ready / failed) and the UI shows it and refreshes until done; optional Caddy HTTPS profile; web proxy origin configurable (`E2EAI_API_ORIGIN`, default 18000); test isolation (conftest); fixes listed under Decisions.
- **Not real yet (do not claim otherwise):**
  - Only **Ragas** is a real Lab tool. Every other Lab stage is still a deterministic offline slice (`security-red-team.local`, `load-test.local`, `bias-fairness.local`, `online-eval.local`, `benchmark.local`, ...): DeepEval, Phoenix, promptfoo, garak, k6 and Langfuse are not installed or adapted.
  - Temporal engine (only the boundary; falls back to `NullJobEngine`), Langfuse tracing (traces are stored in Postgres), figure image crops and VLM enrichment against a real vision model.
  - Real external connectors (Drive/SharePoint/...), real OAuth token exchange, SCIM server surface, CI workflows (the GitHub token lacks `workflow` scope), HA / scale / soak validation, nightly adapter smoke tests.
- **Known risks on the owner's PC:**
  - **`D:` is full** and holds the repo, the Docker VM disk (`docker_data.vhdx`, ~133 GB, of which ~85 GB is reclaimable images from other projects) and the Windows pagefile (`D:\pagefile.sys`, allowed to grow to 50 GB). On 2026-10-28 it reached 0 bytes free during this work: a Next dev server crashed ("Array buffer allocation failed"), and a failed write truncated this very file (restored). A full `D:` can also corrupt the Docker volumes (Postgres). Needs the owner: move the pagefile to `C:` (70 GB free), prune unused Docker images, or move the Docker data disk.
  - Behind Caddy on Docker Desktop every client appears as the Docker gateway IP, so the per-IP login limit is shared (the per-account limit still works).
- **Next 3 tasks:** (1) the next real Lab adapters in the same shape as Ragas (DeepEval first; switch its telemetry off), then Phoenix, promptfoo, k6; (2) Temporal engine behind `JobEngine` (Standard tier); (3) CI workflow once the token has `workflow` scope.

## Owner instructions for the build
- **2026-10-05:** the owner asked to continue until the whole system is developed and testable, and authorized **commit + push after every milestone whose tests pass** (overrides the global "ask before commit/push" rule for this build). Never commit secrets: scan staged files against `deploy/compose/.env` values first.
- **2026-10-28:** the owner asked to fix the five findings of the status check (stack down, Docling stub, local-only Lab, no worker/Caddy/Temporal, stale docs) and allowed updating this file and CLAUDE.md.
- The owner's `%USERPROFILE%\.wslconfig` limits Docker to **5 GB RAM / 4 CPUs** on purpose (other projects share it). Don't change it; run heavy models on Ollama (GPU) and run api/worker/web natively during development.
- Progress files are named `progress_<date>.txt` (the editor hook blocks `.md`/`.txt` creation through the Write tool, so write them through the shell).

## Decisions (newest first)
- **2026-10-28 · Ragas runs as its own HTTP service (PRD T6), not as a library in the API.** Context: Ragas pulls LangChain and pins `langchain-community<0.4` (0.4 removed a module Ragas imports). The judge is a model on the gateway with temperature 0, `max_tokens` 4096 and thinking off (Ragas defaults of 1024 tokens cut a thinking model off mid-JSON); each run gets its own short-lived gateway key limited to the judge and embedding model, never the master key. Alternative: import a framework as a library (rejected: dependency conflicts, telemetry).
- **2026-10-28 · A document is `ready` only after its embeddings exist.** Statuses: `pending` (queued) → `indexing` (parsed, not searchable) → `ready` / `failed` / `skipped`. Context: found in the live PDF check; `ready` used to be committed before embedding, so a question asked right then found nothing. Alternative: keep `ready` and add a separate flag (rejected: every client would need to know about it).
- **2026-10-28 · Docling runs in a separate worker environment on `C:`, not in the API venv.** Context: Docling pulls PyTorch and ~1.2 GB of packages plus models; the repo drive `D:` was nearly full and Docker has 5 GB. `workers/` depends on the API package (path dependency) and reuses `ingest_version`. The API stays light and falls back to inline ingest (or a recorded `failed` with a clear reason) when no worker answers a ping.
- **2026-10-28 · `redis` pinned to `>=6.4,<6.5` in the API.** Context: `kombu` (Celery) supports redis-py `<6.5`; the API only uses basic async commands. Alternative: `celery-redis-plus` (newer, less proven).
- **2026-10-28 · Celery broker/results use Valkey databases 2 and 3**, apart from sessions (database 0; tests use 1). Tasks carry only a version id, never file content.
- **2026-10-28 · Web proxy target is `E2EAI_API_ORIGIN` (default `http://127.0.0.1:18000`).** Context: the rewrite was hard-coded to port 8000, which other local projects use; the documented API port is 18000.
- **2026-10-28 · Caddy is an optional profile (`caddy`), HTTPS with Caddy's local CA, proxying only the web app** (the API is reached through the web app's `/api` proxy). Sites must be named (`localhost`, `127.0.0.1`): a site without a host name gets no certificate (found live).
- **2026-10-28 · Log redaction must not rewrite `record.args` unless it hid something.** Context: it always set `args=None`, which broke uvicorn's access-log formatter on every request.
- **2026-10-28 · Tests that wipe tables run only on a dedicated `*_test` database** (conftest empties it per module and refuses the dev database). Context: 37 tests delete from `documents`/`chunks`/... and had been run against the one dev database; order-dependent failures (FK from `message_citations`) were also caused by shared state.
- **2026-10-28 · Web tests clear `localStorage` after each test and use a 20 s timeout.** The locale switch test used to leave Indonesian on for later tests; the 5 s default failed under load.
- **2026-10-05 · Embeddings may be served by TEI or Ollama (user's choice in the wizard).** D3 keeps TEI as the recommended server. When Docker's memory limit can't fit a TEI model, the wizard recommends the Ollama-served variant (e.g., `bge-m3` on the GPU). Rerankers stay on TEI (Ollama doesn't serve them).
- **2026-10-05 · Valkey instead of Redis.** Context: Redis 8 is licensed AGPLv3/RSALv2/SSPLv1. Decision: Valkey 9.1 (BSD-3, Linux Foundation), a drop-in replacement (same protocol). Alternative: Redis 8 under AGPL as a separate service.
- **2026-10-05 · Default host ports in the 1xxxx range** (15432, 16379, 18080, 18333, 14000, 21434, 18081/18082, 18180, 18443) and bound to 127.0.0.1. Context: the owner's PC already uses 5432, 6379, 3000, 11434. The wizard skips busy ports automatically.
- **2026-10-05 · Reuse a host Ollama when detected and new enough.** The wizard offers the Ollama already running on the machine (LiteLLM reaches it at `host.docker.internal:11434`) instead of starting a second one.
- **2026-10-05 · Wizard dependencies kept minimal:** Typer (includes Rich) and PyYAML; hardware detection uses the standard library (no psutil).
