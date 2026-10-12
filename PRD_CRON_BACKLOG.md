# E2EAIDEV PRD Cron Backlog

Purpose: this is the ordered task list for the 15-minute Hermes cron job `E2EAIDEV auto-resume PRD development`.

Rules for every cron tick:
- Work from the top of this list downward.
- Before starting an item, re-check `progress_2026-10-05.txt`, git log, and source/tests; if the item is already truly implemented and verified, mark it done in progress and move to the next item.
- Complete one small vertical slice per tick when possible: failing test -> implementation -> focused tests -> progress update -> secret scan -> commit -> push -> verify remote.
- Use Claude Code first if available; if Claude is rate-limited or fails, continue manually with Hermes. Do not use Codex.
- Keep tests focused and adjacent, per user preference.
- Never edit `AGENTS.md` without explicit user permission.

## Active priority queue

### A. Finish remaining P1 Lab / Test / Release capabilities
1. [x] [FR-T11] Benchmark runner: model x prompt x dataset leaderboard with quality, p50/p95 latency, TTFT, tokens/s, and cost. Completed as deterministic/offline benchmark.local slice; see progress_2026-10-05.txt.
2. [x] [FR-T5] Judging modes: LLM-only multi-judge majority vote, human-only, and hybrid routing for low confidence/disagreement/audit. Pure service helpers `majority_vote`/`judge_items` in eval_lab.py with safe human-queue storage; see progress_2026-10-05.txt.
3. [x] [FR-T13] Document-understanding test set: table QA, chart QA, figure/diagram QA, OCR character-error-rate, and safety-warning-included checks. Completed as deterministic/offline doc-understanding.local slice; see progress_2026-10-05.txt.
4. [x] [FR-T8] OWASP LLM security tests / red-team suites with promptfoo/garak boundaries. Completed as deterministic/offline `security-red-team.local` slice (prompt injection, data exfiltration, sensitive disclosure, unsafe tool use, over-refusal) with a promptfoo/garak adapter boundary metadata map and leak-safe EvalRun storage; see progress_2026-10-05.txt.
5. [x] [FR-RL2] Release gates: eval thresholds, zero permission leaks, red-team pass, human sign-off. Completed as deterministic/offline per-bot release-gate slice; see progress_2026-10-05.txt.
6. [x] [FR-RL6] Environments: dev -> staging -> prod promotion model, with Lite-tier simplified mode. Completed as a focused bot-environment promotion slice; see progress_2026-10-05.txt.

### B. Operate / analytics / feedback loop P1
7. [x] [FR-O5] SLOs and alerting: latency, error rate, cost per conversation, guardrail trigger rate. Completed as deterministic metrics, DB-backed window aggregation/persistence, guardrail audit aggregation, admin/evaluator notification delivery, and safe dashboard/report API; see progress_2026-10-05.txt.
8. [x] [FR-O6] FinOps: spend per user/team/division/bot, budgets, alerts, chargeback reports.
   - [x] Deterministic/offline service + API slice: aggregate spend by user/team/division/bot from safe metadata events, evaluate budget alerts, and build safe chargeback reports. See progress_2026-10-05.txt.
   - [x] DB-backed spend aggregation from persisted message/token metadata, with conversation bot grouping and a safe rolling-window API. See progress_2026-10-05.txt.
   - [x] Persist/deliver FinOps budget alerts and expose dashboard/report integration. `FinopsBudgetAlert` model + migration 0016, persist/notify/dashboard helpers, POST /finops-window + GET /finops-dashboard. See progress_2026-10-05.txt.
9. [x] [FR-O7] Usage and ROI analytics: active users, questions per division, answer rate, deflection, unanswered topics, estimated time saved.
   - [x] Deterministic/offline service + API slice: aggregate active users, questions per division, answer rate, deflection, top unanswered topics, and estimated time saved from safe usage events. See progress_2026-10-05.txt.
   - [x] DB-backed usage/ROI aggregation from persisted chat/feedback/trace metadata, with safe rolling-window dashboard/report integration. See progress_2026-10-05.txt.
10. [x] [FR-I2] Top unanswered questions report for knowledge owners. Completed as deterministic/offline safe knowledge-gap report + API route (`POST /api/v1/improve/top-unanswered`) with topic/count/division breadth ranking; see progress_2026-10-05.txt.
11. [x] [FR-B3] Structured-output tests: JSON/schema validity rate per model. Completed as deterministic/offline structured-output validity slice with per-model JSON/schema rates, safe item-level error codes, and API route; see progress_2026-10-05.txt.

### C. Live tools / MCP / systems integration P1
13. [x] [FR-B4] Live tools through MCP: one MCP server per system generated from OpenAPI.
   - [x] OpenAPI-to-MCP descriptor generator slice: validate minimal OpenAPI 3.x spec, build safe MCPServerDescriptor/MCPToolDescriptor with allowed operations, read_only defaults (GET=True, mutating=False), explicit overrides, no auth secrets or server URLs in output. POST /api/v1/systems/{system_id}/mcp-descriptor. See progress_2026-10-05.txt.
14. [x] [FR-X2] Live system tools are called at question time through MCP; data is not copied into vectors. Completed as planner + persisted/audited chat pipeline + MCPClientExecutor boundary behind delegated identity; live results are citation-only/sanitized and never vectorized. See progress_2026-10-05.txt.
   - [x] Deterministic/offline question-time MCP tool-call planner and no-vectorize guard: selects safe tool-call records from generated descriptors, flags mutating tools for confirmation, exposes a safe plan API, and rejects live MCP results before embedding/indexing. See progress_2026-10-05.txt.
   - [x] Wire the planner into the chat answer pipeline with persisted/audited tool-call records and an offline executor boundary (no real MCP network calls in tests). See progress_2026-10-05.txt.
   - [x] Add real MCP client execution behind delegated identity once FR-X3 is in progress: MCPClient protocol + MCPClientExecutor boundary, intended to be wrapped by DelegatedExecutor so user-data calls validate delegated/token-exchange identity before execution. See progress_2026-10-05.txt.
15. [x] [FR-X3] AI acts as the real user using delegated identity/token exchange.
   - [x] Deterministic/offline delegated-identity boundary: AuthMode enum (DELEGATED/TOKEN_EXCHANGE/SERVICE_ACCOUNT), DelegatedIdentityContext (safe metadata only, no raw tokens), validate_identity_for_user_data (rejects SERVICE_ACCOUNT, rejects empty user_id), DelegatedExecutor wrapping Executor protocol, safe audit metadata, McpToolCall auth_mode + acting_user_id persistence, API validation route. See progress_2026-10-05.txt.
   - [ ] Real external OAuth provider / token exchange integration (deferred: requires external IdP setup).
16. [x] [FR-X4] Admin flow to register a system, upload OpenAPI spec, choose endpoints, configure auth, test, and grant roles. Completed as deterministic/offline admin flow boundary with SystemRegistration/SystemGrant DB models, migration 0019, 6 admin API routes, and safe output contracts. See progress_2026-10-05.txt.
17. [x] [FR-X5] Read-only by default; write actions require explicit confirmation and audit. Completed as deterministic/offline write-confirmation flow: confirm/deny pending tool calls, safe audit, API route. See progress_2026-10-05.txt.
18. [x] [FR-X6] Answers combine documents and live data with citations for document pages and system record IDs. Completed as deterministic combined-citation builder merging doc citations (source=document, page, section) and executed live MCP tool-call citations (source=live_system, system_id, operation_id, record_id when present). See progress_2026-10-05.txt.

### D. Retrieval/model quality P1
19. [x] [FR-R4] Hybrid search: dense + sparse/BM25 fused with reciprocal rank fusion. Completed: `hybrid_search.py` (tokenize, Okapi BM25, RRF k=60) + `mode="hybrid"` in `retrieve_relevant_chunks` (dense pool + Postgres full-text pool under the same SQL permission filters, fused by RRF) + `retrieval_mode` on `answer_question`/`AskIn`. See progress_2026-10-05.txt.
20. [x] [FR-R6] Query rewriting and conversation-aware follow-up questions. Completed: deterministic/offline `query_rewrite.py` (EN/ID follow-up detection, topic expansion from the user's own prior questions) wired into `chat.send_message` (default on, `rewrite_query` opt-out in API); see progress_2026-10-05.txt.
21. [x] [FR-R2] Reranker selectable per bot, including `none`. Completed: TEI reranker protocol/client + safe selector, bot bundle `reranker` resolution (`none` skips), and reranked answer path after permission/guardrail filtering. See progress_2026-10-05.txt.
22. [x] [FR-M3] Model routing: simple queries to small model, complex to large model, rules/classifier, fallback. Completed: deterministic/offline query complexity classifier + small/large routing with large-model fallback. See progress_2026-10-05.txt.
23. [x] [FR-M4] Semantic/prompt caching keyed on permission set. Completed: safe `semantic_cache.py` permission-set hash/key helpers, in-memory semantic/prompt cache boundary, optional answer-path cache hit/miss wiring, and safe audit metadata; cache entries never cross permission principal sets. See progress_2026-10-05.txt.
24. [x] [FR-M2] vLLM serving engine selectable for GPU profile, behind the serving interface. Completed: vLLM catalog `served_by`, GPU-only fit gate, wizard/env/config support, pinned compose vLLM service, GPU compose reservation, and LiteLLM OpenAI-compatible routing. See progress_2026-10-05.txt.

### E. Data/document P1
25. [x] [FR-D7] Data quality checks: duplicate/near-duplicate detection, stale documents, unparseable files. Completed: pure/offline title duplicate + near-duplicate checks, stale document freshness check, and unparseable status/error detection. See progress_2026-10-05.txt.
26. [x] [FR-D11] Labeling and annotation for gold sets and fine-tuning data. Completed as deterministic/offline dataset annotation slice: versioned eval datasets with gold/fine-tuning labels, safe annotation export, and API route; see progress_2026-10-05.txt.
27. [x] [FR-D15] Optional VLM add-on: routing for figure-heavy/flagged pages, derived output labels, permissions, async enrichment. Completed as deterministic/offline VLM enrichment boundary (routing, async plan, derived chunk labels + document permission inheritance); see progress_2026-10-05.txt.
28. [x] [FR-D16] Technical/maintenance manuals: procedure-step/figure links, parts/torque/spec tables, verbatim safety warnings. Completed as deterministic/offline manual-understanding helpers; see progress_2026-10-05.txt.
29. [x] [FR-D4] Complete selectable chunking modes beyond structure-aware: recursive, semantic, parent-child. Completed as deterministic chunking.py with recursive/semantic/parent-child modes and a select_chunker; safe chunking tests; see progress_2026-10-05.txt.
30. [x] [FR-C6] Derived content inherits strictest permissions of sources. Completed as deterministic derived-permissions helpers (strictest-level inheritance, no per-user principal expansion, secret-safe output); see progress_2026-10-05.txt.
31. [x] [FR-C7] Chat history after access revocation hides revoked citations with source-no-longer-accessible notice. Completed as deterministic/revoked-citations helpers; see progress_2026-10-05.txt.

### F. Platform foundation gaps / hardening P0-P1
32. [x] [FR-F8] Tool adapter framework with standard interface and contract tests for every Lab tool.
    - [x] `tool_adapter.py`: `ToolAdapter` protocol, `ToolCapabilities`, `AdapterHealth`, `ToolAdapterRegistry`,
      `check_adapter_contract` / `check_registry_contract`. Tests: `test_us_tool_adapter_p1.py` (8 passed).
    - Verified: `cd apps/api && uv run pytest -q tests/test_us_tool_adapter_p1.py` -> 8 passed.
33. [x] [FR-F20] Job/workflow engine interface: Celery default P0 and Temporal P1 boundary/contract tests.
    - [x] `job_engine.py`: `JobEngine` protocol, `NullJobEngine`, `check_job_engine_contract`,
      `make_celery_engine`/`make_temporal_engine` with NullJobEngine fallback. Tests: `test_us_job_engine_p0.py` (16 passed).
    - Verified: `cd apps/api && uv run pytest -q tests/test_us_job_engine_p0.py` -> 16 passed.
34. [x] [FR-F4] Install profiles: core, lab-stage, lab-all, GPU/CPU variants for compose/Helm. Completed as deterministic CLI profile contract helpers: core/lab-stage/lab-all, CPU/GPU Compose file selection, explicit model service profiles, and a Helm values boundary; see progress_2026-10-05.txt.
35. [x] [FR-F1] OIDC SSO option and identity-provider-down fallback path integration.
   - [x] Secret-free OIDC authorization URL helper + OIDC-mode local password fallback policy (break-glass only, normal users must use SSO). See progress_2026-10-05.txt.
   - [x] OIDC callback/token validation against bundled Keycloak and user/session creation. Completed as deterministic callback boundary using Keycloak token + userinfo endpoints; see progress_2026-10-05.txt.
36. [x] [FR-F2] Complete Org -> Division -> Team -> User and roles/project scoping gaps; leave SCIM sync for P2.
   - [x] Project containers and project-scoped role grant boundary: `Project` ORM/migration, nullable `UserRole.project_id`, and safe role-scope helpers. See progress_2026-10-05.txt.
   - [x] Admin/service CRUD for divisions, teams, users, memberships, role grants, and project ownership. See progress_2026-10-05.txt.
37. [x] [FR-F7] Harden LiteLLM gateway virtual keys/budgets/fallbacks beyond current baseline. Completed as deterministic wizard/config hardening: DB-backed key management, upper/default virtual-key budgets, key alias pattern, fallback model access/budget enforcement, and generated chat fallback chains. See progress_2026-10-05.txt.
38. [x] [FR-F11] Finish remaining in-app notification types: review assigned, release approved, incident raised; email stays P2. Completed as safe in-app notification service + API boundary for review.assigned/release.approved/incident.raised; see progress_2026-10-05.txt.
39. [x] [FR-F16] Upgrade procedure P2 prep: pre-upgrade backup, health check, rollback notes/tests. Completed as secret-free CLI upgrade-plan helper + runbook with version-window validation and focused tests; see progress_2026-10-05.txt.
40. [x] [FR-F22] P1 docs: generated OpenAPI/API reference and Lab adapter developer guide. Completed: generated OpenAPI JSON + EN/ID API reference from FastAPI schema, EN/ID Lab adapter developer guide, docs validator coverage; see progress_2026-10-05.txt.
41. [x] [FR-F21] P1 export from UI for configuration-as-code. Completed as secret-safe admin API/UI export to YAML/JSON with audit and EN/ID UI link; see progress_2026-10-05.txt.

### G. Learning/UI P1
42. [x] [FR-E2] Why-it-matters enterprise panels per lifecycle stage with OWASP/NIST/EU AI Act/ISO/UU PDP links. Completed as EN/ID accessible lifecycle panels with framework/regulation links; see progress_2026-10-05.txt.
43. [x] [FR-F14] Continue WCAG 2.1 AA accessibility hardening beyond existing EN/ID i18n. Completed as keyboard skip-link/main-focus target and localized feature navigation landmark hardening; see progress_2026-10-05.txt.

### H. P2 compliance / enterprise / connectors after P1 queue
44. [x] [FR-P1] Use-case intake form. Completed as deterministic/offline Plan-stage intake API/service slice capturing problem, users, task-success/deflection/time-saved metrics, data sources, and systems to integrate with safe audit metadata; see progress_2026-10-05.txt.
45. [FR-P2] AI risk classification per bot.
46. [FR-P3] AI inventory with model cards/system cards.
47. [FR-P4] Approval workflow for high-risk bots.
48. [FR-F6] Air-gapped install bundle.
49. [FR-F10] Audit export to SIEM.
50. [FR-F17] Secret/certificate rotation.
51. [FR-D8] Review owner/review date/expiry lifecycle.
52. [FR-D10] Dataset/index lineage.
53. [FR-D13] Legal hold completion for chats and retention interactions.
54. [FR-M7] Model registry with lineage/eval scores/approval status.
55. [FR-M8] Model file security: safetensors, pickle scanning, checksums/signatures.
56. [FR-T9] Bias/fairness tests.
57. [FR-T10] Load tests on model endpoints/full chat API.
58. [FR-RL4] Rollout strategies: shadow/canary/A-B flags.
59. [FR-O3] Online evaluation on sampled production traffic.
60. [FR-O4] Drift detection.
61. [FR-O8] AI incident management.
62. [FR-I1] Data flywheel from feedback to eval/fine-tune/release.
63. [FR-E3] Guided sample scenarios.
64. [FR-X1] Knowledge connectors with permission mirroring.
65. [FR-X7] Ready-made connector templates.
66. [FR-C15] Optional OpenAI-compatible bot model endpoint for external chat frontends.
67. [FR-S8] Org-change-driven access updates from SCIM.

### I. P3 / long-horizon after P2
68. [FR-M5] Quantization lab.
69. [FR-M6] Fine-tuning and distillation.
70. [FR-R9] Advanced RAG: GraphRAG/multimodal/routing across knowledge bases.
71. [FR-R10] Structured-data questions over spreadsheets/CSV with computation.
72. [FR-B5] Agent workflows and trajectory evaluation.
73. [FR-O10] GPU scheduling/sharing.
74. [FR-E4] Role-based learning paths.

### Z. Deferred until CI/deploy is needed
75. [FR-RL3] CI integration for eval suites in GitHub Actions / GitLab CI. Deferred per user because current development should not be blocked by workflow permission/CI setup. Saved local backup branch `deferred/fr-rl3-ci-workflow` and patch `C:/Users/riqan/AppData/Local/hermes/cache/scratch/e2eaidev_fr_rl3_ci_deferred.patch`.

## Notes
- Items already completed before this file should not be repeated; cron must verify and skip them.
- If an item is too large for one tick, split it into sub-slices and record the sub-slice in `progress_2026-10-05.txt`.
- Keep this backlog updated when a task is completed or split.
