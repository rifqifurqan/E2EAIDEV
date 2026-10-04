# CLAUDE.md — E2EAIDEV

Self-hosted **End-to-End Enterprise AI Development Lab**. It covers each lifecycle stage (Plan → Data → Build → Test → Release → Operate → Improve), with enterprise tools installed side by side for comparison. The reference product is a **permission-aware RAG chatbot**: documents are shared Google-Drive-style, and the chatbot calls ERP/HR APIs as the asking user.

## Source of truth
1. [E2EAIDEV_PRD.md](E2EAIDEV_PRD.md): requirements (FR-/NFR- IDs), priorities, phases, and the **build contract in §17**. It wins over everything else.
2. [README.md](README.md): research, tool catalog, architecture rationale. It may lag behind the PRD.
3. `AGENTS.md`: created in Phase 0 (PRD §17.7). It holds setup and conventions plus the **Progress** and **Decisions** sections. Read it at the start of each session.

## Current status
- **Planning done, no code yet.** Next: **Phase 0** (PRD §13): repo skeleton, **Lite tier first** (PRD §12; this PC is Lite-class), CLI install wizard with model selection, OIDC, org model, OpenFGA, adapter framework, audit log.
- Update this section when a phase completes.

## Build rules (summary of PRD §17; read the full section)
- **Strict phase order.** Build only the current phase's priority (P0 = Phase 0–1). Don't start later-phase features early, even partially.
- **Thin slices first.** First Phase 1 slice: upload PDF → parse → embed → share with Andi → Andi gets a cited answer → Budi gets nothing.
- **Done means** code + tests + audit events + leak-suite coverage (if the change touches docs or chat) + docs + the requirement ID in the commit message.
- **Decide and log** reversible implementation choices in the Decisions section of `AGENTS.md`. **Ask the owner first** about scope changes, PRD contradictions, security/permission-model changes, new license classes (AGPL, ELv2, non-commercial), paid services, or hard-to-reverse changes.
- **Pin everything.** No `latest` tags or unpinned installs; record versions in `deploy/versions.lock`. Never install `litellm` from PyPI unpinned (supply-chain incident, March 2026).
- **No hardcoded default models.** The user picks models in the install wizard (FR-F5a).
- **Before introducing a tool, re-verify** its license, maintenance status, and security advisories from primary sources.

## Non-negotiables
- **Permissions:** index once, filter by permission **inside** the vector query (never filter after top-k). Caches are keyed on the user's permission set. Derived content inherits the strictest permissions of its sources. A permission-leak test failure blocks the change.
- **Live system tools** (ERP/HR) run as the real user (token exchange), never as a super-admin account. Read-only unless the user confirms the action.
- **Each Lab tool runs in its own container** behind an adapter with contract tests. Never mix tool dependencies into one Python environment.
- **Secrets** never go in code, the database, or logs.

## Planned layout (PRD §17.2)
`apps/api` (FastAPI, Python 3.12, uv) · `apps/web` (Next.js, TypeScript, pnpm) · `workers/` · `adapters/<stage>/<tool>/` · `cli/` (wizard, Typer) · `catalog/{models,tools}.yaml` · `deploy/{compose,helm,versions.lock}` · `tests/e2e/` (one test per user story, e.g. `test_us03_budi_sees_nothing.py`) · `docs/`

## Commands
- `cd cli && uv run e2eai`: install wizard (services, ports, usernames/passwords → `deploy/compose/.env`, `e2eai.yaml`). `--yes` accepts defaults; `--force` replaces an existing `.env` (a backup is kept).
- `cd cli && uv run pytest -q`: wizard tests.
- `cd deploy/compose && docker compose config --quiet`: validate; `docker compose up -d`: start infra (check ports/servers first, per global rules).
- Planned: `make verify-phase-N` (no `make` on the owner's Windows PC yet; use uv scripts until decided).

## Dev machine (owner's PC)
- Windows 11, Docker Desktop with WSL2 (Ubuntu), 16 threads, ~22 GB RAM.
- Raise the WSL memory limit to ~14 GB in `%USERPROFILE%\.wslconfig` before running the full `core` profile.
- **GPU: RTX 3060 Laptop, 6 GB VRAM.** Ollama with small quantized models works. **vLLM doesn't fit**: test the GPU profile on a rented cloud GPU.
- System Python is 3.10. Use `uv` to get 3.12 per project; never change the system Python. Node 20 is available.
- Langfuse (ClickHouse) is heavy: keep it in its own profile on this machine.

## Working with the owner
- Git: never commit or push unless explicitly asked. No Claude/Anthropic attribution in commits (see global CLAUDE.md).
- **Push auth:** git's saved HTTPS credential is a different account (`jihanint`), and SSH only works for the `ieko-media` org. Push with:
  `git -c credential.helper= -c "credential.helper=!gh auth git-credential" push`
- Remote: https://github.com/rifqifurqan/E2EAIDEV
- The everything-claude-code plugin hook blocks the Write tool from creating `.md`/`.txt` files other than README/CLAUDE/AGENTS/CONTRIBUTING. Progress and decisions therefore live inside `AGENTS.md`, by owner decision (no separate PROGRESS/DECISIONS files).
- The owner writes in English or Indonesian; reply in the language they used.
