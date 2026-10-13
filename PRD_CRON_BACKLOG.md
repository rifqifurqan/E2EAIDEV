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
12. [x] [FR-D2] S3-compatible object storage. Completed as SeaweedFS/S3 adapter behind the document storage interface with content-addressed keys and local test fallback; see progress_2026-10-05.txt.

### C. Live tools / MCP / systems integration P1
13. [x] [FR-B4] Live tools through MCP: one MCP server per system generated from OpenAPI.
   - [x] OpenAPI-to-MCP descriptor generator slice: validate minimal OpenAPI 3.x spec, build safe MCPServerDescriptor/MCPToolDescriptor with allowed operations, read_only defaults (GET=True, mutating=False), explicit overrides, no auth secrets or server URLs in output. POST /api/v1/systems/{system_id}/mcp-descriptor. See progress_2026-10-05.txt.
14. [x] [FR-X2] Live system tools are called at question time through MCP; data is not copied into vectors. Completed as planner + persisted/audited chat pipeline + MCPClientExecutor boundary behind delegated identity; live results are citation-only/sanitized and never vectorized. See progress_2026-10-05.txt.
   - [x] Deterministic/offline question-time MCP tool-call planner and no-vectorize guard: selects safe tool-call records from generated descriptors, flags mutating tools for confirmation, exposes a safe plan API, and rejects live MCP results before embedding/indexing. See progress_2026-10-05.txt.
   - [x] Wire the planner into the chat answer pipeline with persisted/audited tool-call records and an offline executor boundary (no real MCP network calls in tests). See progress_2026-10-05.txt.
   - [x] Add real MCP client execution behind delegated identity once FR-X3 is in progress: MCPClient protocol + MCPClientExecutor boundary, intended to be wrapped by DelegatedExecutor so user-data calls validate delegated/token-exchange identity before execution. See progress_2026-10-05.txt.
15. [x] [FR-X3] AI acts as the real user using delegated identity/token exchange.
   - [x] Deterministic/offline delegated-identity boundary: AuthMode enum (DELEGATED/TOKEN_EXCHANGE/SERVICE_ACCOUNT), DelegatedIdentityContext (safe metadata only, no raw tokens), validate_identity_for_user_data (rejects SERVICE_ACCOUNT, rejects empty user_id), DelegatedExecutor wrapping Executor protocol, safe audit metadata, McpToolCall auth_mode + acting_user_id persistence, API validation route. See progress_2026-10-05.txt.
   - Deferred to Z: real external OAuth provider / token exchange integration requires external IdP setup and credentials.
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
24.1. [x] [FR-M1] Register model endpoints and test them through the gateway/playground. Completed as secret-safe LiteLLM registration payload builder plus admin playground probe API; see progress_2026-10-05.txt.

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
45. [x] [FR-P2] AI risk classification per bot. Completed as deterministic/offline bot risk classification slice with EU AI Act tier, NIST AI RMF profile, UU PDP impact level, derived release-gate requirements, safe audit metadata, and API route; see progress_2026-10-05.txt.
46. [x] [FR-P3] AI inventory with model cards/system cards. Completed as deterministic/offline governance inventory slice with safe model/system cards, owner/risk/status/approval metadata, audit, migration 0023, and API route; see progress_2026-10-05.txt.
47. [x] [FR-P4] Approval workflow for high-risk bots. Completed as deterministic/offline bot approval workflow with request/decision records, inventory approval-state sync, safe audit metadata, migration 0024, and API routes; see progress_2026-10-05.txt.
48. [x] [FR-F6] Air-gapped install bundle. Completed as deterministic/offline air-gap bundle planning slice with pinned image tarball commands, local model mirror plan, offline docs copy plan, floating-image guard, and CLI command; see progress_2026-10-05.txt.
49. [x] [FR-F10] Audit export to SIEM. Completed as deterministic/offline syslog/OpenTelemetry/webhook payload exporter with cursoring, secret-safe details handling, and API route; see progress_2026-10-05.txt.
50. [x] [FR-F17] Secret/certificate rotation. Completed as deterministic/offline slice: API-key rotation with grace overlap, immediate emergency revoke (audited, no raw keys), project-charset secret generator, 14-day certificate expiry status, zero-downtime rotation plan, and 4 admin routes under `/api/v1/security`; see progress_2026-10-05.txt.
51. [x] [FR-D8] Review owner/review date/expiry lifecycle. Completed: `documents.review_owner_id/review_at/expires_at` (migration 0025), expired documents excluded inside the SQL retrieval/search/visible-chunk filters, due-review report for review owners, mark-reviewed, and 3 routes; see progress_2026-10-05.txt.
52. [x] [FR-D10] Dataset/index lineage. Completed: `index_lineage` table (migration 0026) recording document version, parser, chunker, and embedding model per index build (written at ingest, idempotent), permission-filtered lineage view, admin summary, and 2 routes under `/api/v1/lineage`; see progress_2026-10-05.txt.
53. [x] [FR-D13] Legal hold completion for chats and retention interactions. Completed: `conversations.legal_hold` (migration 0027), admin-only hold/release for documents and chats, held chats blocked from user deletion (409), retention sweep (dry-run default) that skips held chats/documents, and 4 routes under `/api/v1/legal-hold`; see progress_2026-10-05.txt.
54. [x] [FR-M7] Model registry with lineage/eval scores/approval status. Completed: `model_registry_entries` (migration 0028), versioned entries with sanitized lineage + parent chain, numeric eval-score snapshots from existing EvalRun, admin-only approval requiring >= 1 score, and 5 routes under `/api/v1/model-registry`; see progress_2026-10-05.txt. MLflow integration remains a follow-up.
55. [x] [FR-M8] Model file security: safetensors, pickle scanning, checksums/signatures. Completed as deterministic/offline static checks: format classification (safetensors/GGUF preferred, pickle formats high-risk), opcode-level pickle scan that never executes the pickle (fail closed when unparseable; also scans torch zip `.pkl` members), sha256 checksum verification, HMAC manifest signature verification, allow/warn/block verdict, and 2 admin routes under `/api/v1/model-security`; see progress_2026-10-05.txt. Sigstore/cosign-style public-key signatures remain a follow-up.
56. [x] [FR-T9] Bias/fairness tests. Completed as deterministic/offline `bias-fairness.local` slice: per-attribute group refusal-rate and mean-score gaps with thresholds, counterfactual pair consistency (same question, only the group changes), safe EvalRun storage (labels/rates/pair ids only, no prompts or responses), deepeval-bias boundary metadata, and `POST /api/v1/evals/bias-fairness`; see progress_2026-10-05.txt.
57. [x] [FR-T10] Load tests on model endpoints/full chat API. Completed as deterministic/offline `load-test.local` slice: bounded-concurrency async runner with injected target, linear-interpolated p50/p95/p99, throughput, error rate, SLO threshold verdict with per-metric violations, k6 script generator for chat API / model endpoint using env placeholders only (no URLs or credentials), safe EvalRun storage (aggregates only), and 2 routes under `/api/v1/evals/load-test`; see progress_2026-10-05.txt. Real k6/guidellm execution against the live stack remains a follow-up.
58. [x] [FR-RL4] Rollout strategies: shadow/canary/A-B flags. Completed as pure/deterministic `rollout.py` slice: sticky salted-hash bucketing, canary traffic %, shadow mirror (baseline always served), A/B weights, feature-flag off switch, plan validation, promote/continue/rollback decision from online arm metrics, and 2 routes under `/api/v1/rollouts`; see progress_2026-10-05.txt. Persisting plans per bot and wiring `assign` into the chat pipeline remain follow-ups.
59. [x] [FR-O3] Online evaluation on sampled production traffic. Completed as deterministic/offline `online-eval.local` slice: sticky hash sampler, heuristic scorer from safe signals only (answered / has_citation / feedback), per-bot-version aggregation, low-quality alert, allowlisted trace keys (prompts/answers/user ids dropped before processing), safe EvalRun storage, and `POST /api/v1/evals/online`; see progress_2026-10-05.txt. Langfuse evaluator / LLM-judge scorer remains a follow-up.
60. [x] [FR-O4] Drift detection. Completed as pure/deterministic `drift.py` slice: topic shift (Jensen-Shannon + PSI, new/vanished topics), embedding drift (centroid cosine distance + spread ratio), quality decay (mean drop with min-samples guard), combined `detect_drift` verdict, and `POST /api/v1/operate/drift`; see progress_2026-10-05.txt. Scheduled windowing from traces and Evidently adapter remain follow-ups.
61. [x] [FR-O8] AI incident management. Completed: `ai_incidents` (migration 0029), report with severity sev1-4 + linked trace ids (plain ids only) + credential redaction, admin-notified via incident.raised, strict lifecycle reported->triaged->fixing->fixed->released->closed (fix notes, release ref, post-incident record required), audited, and 4 routes under `/api/v1/incidents`; see progress_2026-10-05.txt.
62. [x] [FR-I1] Data flywheel from feedback to eval/fine-tune/release. Completed: `flywheel_items` triage queue (migration 0030; thumbs-down collection idempotent, low-online-score and reviewer flags, PII-masked question/correction only, answer never stored), admin triage (accept needs correction + eval/finetune target), export to versioned gold/fine_tuning EvalDataset, re-eval and release linking, audited, 7 routes under `/api/v1/improve/flywheel`; see progress_2026-10-05.txt.
63. [x] [FR-E3] Guided sample scenarios. Completed as deterministic/offline `scenarios.py` (HR-policy bot, why-does-my-bot-hallucinate, find-the-permission-leak; EN/ID text, synthetic sample data, answer key not exposed, permission-leak answer derived from sample ACLs) + checker and 3 routes under `/api/v1/learn/scenarios`; see progress_2026-10-05.txt.
64. [x] [FR-X1] Knowledge connectors with permission mirroring. Completed as the connector sync framework (`connectors.py`, `connector_documents` migration 0031): `Connector` protocol + `FakeConnector`, source ACL mirrored as read-only local principals (fail closed: unknown users, unmapped groups, public/anyone links dropped), tighten-first revocation before OpenFGA, new version on content change, trash on source deletion, no implicit access for the syncing admin, audit with counts only, and admin-only `POST /api/v1/connectors/sync`; see progress_2026-10-05.txt. Real Drive/SharePoint/Nextcloud/Confluence clients need external credentials and remain deferred.
65. [x] [FR-X7] Ready-made connector templates. Completed as `connector_templates.py`: SAP, Odoo, Talenta/Mekari, Salesforce starter OpenAPI skeletons (no server URLs/security schemes/credentials), per-user auth mode (token_exchange/delegated, never service account), read-only default endpoint selection, `apply_template` via the FR-X4 registration flow (audited, admin-only), and 3 routes under `/api/v1/admin/connector-templates`; templates are starting points flagged `verify_against_vendor_docs`; see progress_2026-10-05.txt.
66. [x] [FR-C15] Optional OpenAI-compatible bot model endpoint for external chat frontends. Completed as `openai_compat.py`: `GET /api/v1/openai/models` (bots with a production bundle the user is granted) and `POST /api/v1/openai/chat/completions` (model = bot id, last user message only, client system prompt/files/tools ignored, unusable and non-existent bots return the same 404, runs `answer_bot_question` = bot scope ∩ user permissions, request/token quotas, non-stream + SSE stream, `citations` extension field); see progress_2026-10-05.txt.
67. [x] [FR-S8] Org-change-driven access updates from SCIM. Completed as `scim_sync.py`: SCIM-style users/groups applied to the org model (email match, department -> division by name, unknown department fails closed with a warning, group -> team membership mirrored exactly, `active=false` deprovisions via FR-F18 offboarding, OpenFGA tuples corrected with removals first, audit counts only) and admin-only `POST /api/v1/scim/sync`; see progress_2026-10-05.txt. A real SCIM 2.0 server surface (bearer-token `/Users` `/Groups` endpoints, PATCH ops) and IdP wiring remain follow-ups.

### I. P3 / long-horizon after P2
68. [x] [FR-M5] Quantization lab. Completed as deterministic/offline `quantization_lab.py` (AWQ/GPTQ/GGUF/fp16 variants compared to a baseline on relative quality loss, speedup, and memory saving; memory estimated from params x bits when not measured; format -> serving-engine compatibility; constraint-based recommendation with rejection reasons) + `POST /api/v1/models/quantization/compare`; see progress_2026-10-05.txt. Running real quantization jobs and live measurement remain follow-ups.
69. [x] [FR-M6] Fine-tuning and distillation. Completed as deterministic/offline `finetune_plan.py` planning layer (LoRA/QLoRA/full/DPO/distillation spec validation, GPU memory estimate + fit check, trainer-neutral config for Unsloth/Axolotl/TRL, training-data check via PII detector + approved label sources reporting indexes/codes only, results -> FR-T11 benchmark combinations with quality delta) + 3 routes under `/api/v1/models/finetune`; see progress_2026-10-05.txt. Actual training execution remains a follow-up.
70. [x] [FR-R9] Advanced RAG: GraphRAG/multimodal/routing across knowledge bases. Completed as deterministic/offline pure `advanced_rag.py` (KB routing by topic overlap restricted to accessible ids with fallback, co-occurrence entity graph + multi-hop chunk expansion over already permission-filtered chunks, chart/figure modality detection EN/ID + rerank boost) + `POST /api/v1/retrieval/route-kbs` and `/graph-expand`; see progress_2026-10-05.txt. Caveat: `accessible_ids` on the route is caller-supplied, so wiring into the chat pipeline must pass server-computed ids. Not yet wired into `answer_question`.
71. [x] [FR-R10] Structured-data questions over spreadsheets/CSV with computation. Completed as deterministic/offline `table_qa.py` (typed CSV parse, structured filter/group-by/aggregate/sort/limit and group comparison executed by plain code, no eval/SQL, formula-cell neutralisation, source file in result) + `POST /api/v1/data/table-query`; see progress_2026-10-05.txt. XLSX parsing and NL-to-query translation remain follow-ups.
72. [x] [FR-B5] Agent workflows and trajectory evaluation. Completed as deterministic/offline `agent_workflow.py` (bounded dependency-ordered workflow validation incl. cycle/duplicate/unknown-dep checks, allow-listed injected tool runner that stops on blocked/failed steps, safe trajectory with tool names + arg keys + status only, trajectory scoring on tool selection/order/arguments/efficiency/final-answer) + `POST /api/v1/agents/workflow/validate` and `/trajectory/score`; see progress_2026-10-05.txt. LangGraph adapter and persisted runs remain follow-ups.
73. [x] [FR-O10] GPU scheduling/sharing. Completed as deterministic/offline `gpu_scheduler.py` Kueue-style planner (inventory validation, priority-then-FIFO admission, per-team memory quotas, exclusive / MIG-slice / time-slice placement, queue reasons, per-GPU utilization) + `POST /api/v1/operate/gpu-schedule`; see progress_2026-10-05.txt. Applying plans to Kubernetes Kueue / NVIDIA device plugin remains a follow-up.
74. [x] [FR-E4] Role-based learning paths. Completed as static bilingual `learning_paths.py` (AI engineer, evaluator, AI PM, compliance, platform; steps tied to lifecycle stages and FR-E3 scenarios, stateless progress calculator) + 3 routes under `/api/v1/learn/paths`; see progress_2026-10-05.txt. Web UI and per-learner stored progress remain follow-ups.

### J. PRD audit gaps (added 2026-10-13, after all listed items were done)
77. [x] [FR-O13] GPU out-of-memory runbook (the only runbook of the PRD minimum set that was missing). Completed: `docs/runbooks/gpu-out-of-memory.md` via `scripts/generate_docs.py`, validator updated, linked from EN/ID admin guides; see progress_2026-10-05.txt. Staging drills of the runbooks remain deferred (need a staging environment).
78. [x] [FR-B2] Long-term user memory (P2). Completed as opt-in (off by default), PII-masked/secret-redacted `user_memories` (migration 0032), owner-only list/delete/clear (foreign id returns 404), content-free audit, `recall_context` helper, and 5 routes under `/api/v1/memory`; see progress_2026-10-05.txt. Wiring `recall_context` into the chat answer pipeline remains a follow-up.

79. [x] [NFR-18/NFR-16/NFR-20] API hardening: security headers, request id, EN/ID problem details. Completed as `core/http_hardening.py` ASGI middleware + `title_id`/`request_id` in problem details; see progress_2026-10-05.txt. Follow-ups: idempotency keys, cursor pagination, OTel export.

80. [x] [NFR-20] Idempotency keys for create operations. Completed as `core/idempotency.py` ASGI middleware with Valkey store (replay, body-mismatch 422, per-principal scope, no raw key/credentials stored, degrade on store outage); see progress_2026-10-05.txt. Follow-up: in-flight duplicate lock.

81. [x] [NFR-20] Cursor pagination. Completed as `core/pagination.py` (opaque keyset cursor, limit clamp, 422 on bad cursor) applied to chat conversations list; see progress_2026-10-05.txt. Follow-up: roll out to the other list endpoints.

82. [x] [NFR-7/NFR-19] Log credential redaction and timeout/retry helper. Completed as `core/log_redaction.py` (filter installed at app start) and `core/resilience.py` (`with_retry`); see progress_2026-10-05.txt. Follow-up: wrap external clients in `with_retry`.

83. [x] [NFR-19] Retry + clear 503 for model/embedding/rerank calls. Completed as `post_json_with_retry` wired into TeiReranker, LiteLLMEmbedder, LiteLLMAnswerGenerator; see progress_2026-10-05.txt. Follow-up: OpenFGA/Keycloak/MCP retry, circuit breaker.

84. [x] [NFR-16] Request metrics and admin Prometheus endpoint. Completed as `core/metrics.py` + `metrics_api.py` (`GET /api/v1/metrics`, admin-only, route-template labels); see progress_2026-10-05.txt. Follow-up: OTLP traces/logs export.

85. [x] [NFR-10] Data-subject requests (export / erase a person's data). Completed as `data_subject.py` (admin-only; erase requires offboarded user, blocked by legal hold, pseudonymises profile, audit retained) and 2 routes under `/api/v1/privacy`; see progress_2026-10-05.txt. Follow-up: traces/vectors erasure, self-service, request ledger with deadlines.

86. [x] [NFR-12] No outbound telemetry by default (LiteLLM, vLLM, TEI). Completed as config/compose opt-outs with tests; see progress_2026-10-05.txt. Follow-up: web (Next.js) and other services, live egress-block verification.

87. [x] [NFR-6] Backup and restore plan with RPO/RTO check. Completed as secret-free `backup.py` + `e2eai backup-plan` CLI with tests; commands NOT yet executed against the live stack. Follow-up: live backup/restore drill (deferred: needs a disposable environment), scheduling, encryption, Langfuse.

88. [x] [NFR-17] License report before install. Completed as `licenses.py`, shown by `e2eai init` before files are written, plus `e2eai licenses`; tool licenses need upstream re-verification. Deferred to owner: repo LICENSE file (Apache 2.0 proposed). Follow-up: dependency license scan, SBOM (NFR-9).

89. [x] [NFR-9] SBOM and supply-chain checks. Completed as `supply_chain.py` + `e2eai sbom` (CycloneDX 1.5, fails on unpinned image or unhashed package; real locks verified). Follow-up (deferred with CI/workflow scope): vulnerability scanning in CI, signed artifacts, web (npm) dependencies.

90. [x] [NFR-16/NFR-19] Dependency-aware readiness. Completed as `core/readiness.py` + `readiness_checks.py` (required postgres/valkey/openfga -> 503; optional model-gateway -> degraded 200; no error text exposed); see progress_2026-10-05.txt.

91. [x] [NFR-20] Cursor pagination rolled out to notifications and incidents lists. Completed with `list_notifications_page` / `list_incidents_page`; see progress_2026-10-05.txt. Follow-up: documents search, flywheel, ai-inventory, model-registry, legal-hold.

92. [x] [NFR-20] Per-user display time zone. Completed as `core/timezones.py` + `preferences.py` (`/api/v1/me/preferences`), plus `tzdata` dependency (zoneinfo had no zone data on this host); see progress_2026-10-05.txt. Follow-up: use `to_user_time` in UI/response formatting; created_by/updated_by on remaining tables.

93. [x] [NFR-19] Bounded retry on OpenFGA checks (transient only, still fail closed). Completed in `authz.py` with `tests/test_authz_retry_nfr19.py`; see progress_2026-10-05.txt. Follow-up: Keycloak/MCP retry, circuit breaker.

94. [x] [NFR-12] Web app (Next.js) telemetry forced off through `apps/web/scripts/next-no-telemetry.mjs` used by dev/build/start; see progress_2026-10-05.txt. Follow-up: opt-outs for the other infra services, live egress-block test.

95. [x] [NFR-20] UI `formatTimestamp` helper (UTC -> user zone, default Asia/Jakarta, EN/ID) in `apps/web/src/lib/time.ts`; see progress_2026-10-05.txt. Follow-up: load the user's zone in the app shell, settings UI.

96. [x] [NFR-19] Guardrail outage: mandatory guard blocks with 503, optional guard degrades (audited, not cached). Completed in `guardrails.py` + `retrieval.py`; see progress_2026-10-05.txt. Follow-up: per-bot mandatory flag; same rule for VLM/Langfuse/Lab tools.

97. [x] [NFR-7] No plaintext credentials in the database: schema allowlist guard + live scan against `.env` secret values (`tests/test_no_plaintext_credentials_nfr7.py`); see progress_2026-10-05.txt. Follow-up: encryption at rest / TLS (deployment).

98. [x] [NFR-18] Login rate limit per account + per client address with `Retry-After` (`auth.login_decision`, `AppError.headers`); see progress_2026-10-05.txt. REQUIRED when Caddy is added: run uvicorn with `--proxy-headers` and a trusted `--forwarded-allow-ips`, otherwise all users share one IP bucket.

99. [x] [FR-B2] Wire opt-in long-term user memory into the chat answer pipeline. Completed: `send_message` now recalls the asking user's memory after owner check and passes it as uncited, untrusted context; memory is guardrail-checked, skipped from rerankers and semantic cache, and never creates document citations; see progress_2026-10-05.txt.

100. [x] [NFR-20/FR-S10] Cursor pagination on permission-filtered document search. Completed: `/api/v1/documents/search` supports `limit`/`cursor`, returns `next_cursor`, and keeps permission filters before pagination; see progress_2026-10-05.txt.
101. [x] [NFR-20] Idempotency in-flight duplicate lock. Completed: concurrent requests with the same scoped idempotency key/body now receive 409 + `Retry-After` while the first request is still running, and do not execute the mutating handler twice; see progress_2026-10-05.txt.

102. [x] [NFR-20] Cursor pagination on the remaining list endpoints. Completed: `queue_page` (flywheel, admin check before page), `list_inventory_page` (AI inventory), `list_models_page` (model registry), `list_holds_page` (legal hold, per kind); all four GET routes accept `limit`/`cursor` and return `next_cursor`; see progress_2026-10-05.txt.

103. [x] [NFR-20] Cursor pagination on API-key and index-lineage lists. Completed: `list_api_keys_page` (owner-scoped, no hashes) and `visible_lineage_page` (document permission predicate in SQL before the page cut); `GET /api/v1/api-keys` and `GET /api/v1/lineage` accept `limit`/`cursor` and return `next_cursor`; see progress_2026-10-05.txt.

104. [x] [NFR-8] Access changes apply in <= 5 s. Completed as characterization tests (`tests/test_access_change_latency_nfr8.py`: team removal, document revoke, disabled user); see progress_2026-10-05.txt. Remaining PRD ids with no code slice: NFR-3/4/5 (hardware/load/HA targets, need GPU/K8s env) and NFR-15 nightly adapter smoke (needs CI workflow scope) -> deferred.

105. [x] [NFR-20] Cursor pagination on bot-approvals, document access-requests and user-memory lists. Completed: `list_bot_approvals_page`, `list_access_requests_page`, `list_memories_page`; the three GET routes accept `limit`/`cursor` and return `next_cursor`; see progress_2026-10-05.txt.

106. [x] [NFR-20] Cursor pagination on prompt versions and due document reviews. Completed: `list_prompt_versions_page`, `list_due_reviews_page`; `GET /api/v1/prompts/{prompt_id}/versions` and `GET /api/v1/documents/reviews/due` accept `limit`/`cursor` and return `next_cursor`; see progress_2026-10-05.txt.

107. [x] [NFR-19] Circuit breaker for model/embedding/rerank calls. Completed: `CircuitBreaker` + `breaker_for` in `core/resilience.py`, optional `breaker=` on `post_json_with_retry` (fail fast 503 + `Retry-After`, half-open probe), wired into TeiReranker/LiteLLMEmbedder/LiteLLMAnswerGenerator; see progress_2026-10-05.txt.

108. [x] [NFR-16/NFR-19] Circuit breaker state exposed as `circuit_breaker_state{upstream}` gauge on the admin Prometheus endpoint (URL-free labels); see progress_2026-10-05.txt.

109. [x] [NFR-19/FR-F1] Bounded retry + clear 503 for Keycloak OIDC token/userinfo calls (token POST retried on connect errors only: single-use code). See progress_2026-10-05.txt.

110. [x] [NFR-20/FR-I1] Flywheel summary counts aggregated in SQL (whole queue, not first 1000 rows) and status filter applied in SQL. Completed in `flywheel.queue_summary`; see progress_2026-10-05.txt. Pagination rollout is now complete: no GET list endpoints remain unpaged except bounded/static ones (bots/evals/connectors expose no list GET).

111. [x] [NFR-19/FR-F1] Circuit breaker for Keycloak OIDC calls (open after repeated outages, fail fast 503 + `Retry-After`, 4xx rejections do not trip it, `circuit_breaker_state{upstream="keycloak"}` gauge). See progress_2026-10-05.txt.

112. [x] [NFR-19/FR-D15] Optional VLM add-on degrades on outage: `run_vlm_enrichment` keeps the baseline parse, fails fast after the first upstream error, reports `failed_pages` + reason code only. See progress_2026-10-05.txt.

113. [x] [NFR-10] Data-subject request ledger with deadlines: `data_subject_requests` (migration 0033), 30-day due date, auto-complete on export/erase, overdue filter, cursor-paginated `GET /api/v1/privacy/requests` + `POST /api/v1/privacy/requests`. See progress_2026-10-05.txt.

114. [x] [NFR-10/FR-F11] Data-subject request deadline reminders: `dsr.deadline` in-app notification to every active admin once per state (due_soon, overdue), `last_reminder` tracking (migration 0034), `POST /api/v1/privacy/requests/remind`. See progress_2026-10-05.txt.

115. [x] [NFR-10/FR-I1] Data-subject erase also deletes flywheel items derived from the subject's answers (they keep a PII-masked question copy); count reported as `flywheel_items_deleted`. See progress_2026-10-05.txt.

116. [x] [NFR-10] Self-service data-subject requests: `GET /api/v1/privacy/me/export` (own data only, audited `dsr.self_export` with counts), `POST/GET /api/v1/privacy/me/requests` (file/list own requests; erase stays an admin action after offboarding). See progress_2026-10-05.txt.

117. [x] [NFR-12] Telemetry opt-outs for the remaining compose services: `OLLAMA_NO_CLOUD=1` (ollama service) and `OPENFGA_TRACE_ENABLED=false` (openfga + migrate), plus a test that every published port binds to `${BIND_ADDRESS}`. Variables verified against upstream docs. See progress_2026-10-05.txt. Live egress-block test still open.

118. [x] [NFR-19/FR-F8] Lab tools degrade instead of failing chat: `run_tool_safely` in `tool_adapter.py` (missing tool -> `unavailable`; error/timeout/open breaker -> `degraded` with reason code only, per-tool breaker `lab:<name>` visible in the circuit_breaker_state gauge). See progress_2026-10-05.txt.

119. [x] [NFR-20] `created_by`/`updated_by` and `created_at`/`updated_at` on every record. Completed: 41 tables gained the missing audit columns (migration 0035; only `audit_log` is exempt, with a reason in `AUDIT_EXEMPT_TABLES`), a `before_flush` hook (`core/audit_actor.py`) stamps the acting principal set by `current_session` (explicit values and no-op changes are never touched), and a schema-wide test fails when a new table lacks the columns. Full API suite 793 passed. See progress_2026-10-05.txt.

120. [x] [FR-R3] `VectorStore` port with Qdrant (P1) adapter and contract check. Completed as `vector_store.py`: mandatory permission filter inside the query (empty set -> nothing, no backend call), ids-only payload, idempotent upsert, delete by document, retry + breaker `vector-store` with URL-free 503, `check_vector_store_contract`, in-memory reference store, `make_vector_store`; see progress_2026-10-05.txt. Follow-up: wire Qdrant into ingest/retrieval selection by `components.vector_store`, add Qdrant compose service.

121. [x] [FR-F21/FR-R3/FR-F20] `components` in e2eai.yaml validated at startup. Completed in `core/config.py`: `ConfigError`, `validate_components` (auth, job_engine, vector_store, tracing; every bad value reported with allowed list; defaults filled), `Settings.vector_store` and `Settings.job_engine`; see progress_2026-10-05.txt. Follow-up: use `Settings.vector_store` in ingest/retrieval, Qdrant compose service.

122. [x] [FR-R3/FR-C2] Retrieval and indexing through an external `VectorStore`. Completed: `index_document_chunks(..., vector_store=)` writes ids-only points, `retrieve_relevant_chunks(..., vector_store=)` sends only SQL-permitted document ids inside the store query and re-checks returned chunk ids with the same SQL predicate (a backend that ignores the filter cannot leak); hybrid mode with an external store is rejected (400); see progress_2026-10-05.txt. Follow-up: select the store from `Settings.vector_store` in the ingest job/chat pipeline, Qdrant compose service.

123. [x] [FR-D9/FR-R3] Ingest and purge propagate to the external `VectorStore`. Completed: `ingest_version(..., vector_store=)` indexes through it; `purge_document(..., vector_store=)` deletes the document's vectors, and a store outage never blocks SQL tightening (audit detail `vector_store_purge` ok|failed, reason code only); see progress_2026-10-05.txt. Follow-up: choose the store from `Settings.vector_store` in the ingest job/API wiring, retry job for failed store purges, Qdrant compose service.

124. [x] [FR-R3] `components.vector_store` now selects the store. Completed: `configured_vector_store(settings)` (cached per endpoint, `pgvector` -> None), `Settings.qdrant_url` / `qdrant_api_key` (`QDRANT_API_KEY` from .env, never in repr), Qdrant collection size taken from the first upserted vector, and ingest / purge / dense retrieval default to the configured store (explicit `vector_store=None` forces SQL-only; hybrid stays on SQL); see progress_2026-10-05.txt. Follow-up: Qdrant compose service + pinned digest, wizard option, retry job for purges flagged failed, live Qdrant run.

125. [x] [FR-R3/NFR-12/NFR-9] Qdrant as an optional P1 install component. Completed: image pinned by digest in `deploy/versions.lock` (qdrant v1.15.5, digest resolved with `docker buildx imagetools inspect`), compose service under profile `qdrant` (API key required, `QDRANT__TELEMETRY_DISABLED=true`, port bound to `${BIND_ADDRESS}`, own volume), wizard `Service`/secret `QDRANT_API_KEY` (generated, >= 16 chars)/license entry, `components.vector_store: qdrant` + `qdrant.url` written when selected, `load_answers` round-trip; see progress_2026-10-05.txt. Follow-up: interactive wizard prompt for Qdrant (currently set via `optional.qdrant`), live Qdrant run + retrieval smoke, retry job for purges flagged failed.

126. [x] [NFR-6/FR-R3] Qdrant volume in the backup/restore plan. Completed: `build_backup_plan` / `build_restore_plan` / `render_backup_runbook` take `qdrant=True` (tar of `e2eai_qdrantdata` to `qdrant.tar.gz`, restore symmetric, target `vector-store` in the runbook), `e2eai backup-plan --qdrant`; default plan unchanged; no secret values (the API key stays inside the private env file); see progress_2026-10-05.txt. Follow-up: derive `qdrant` from e2eai.yaml automatically, drill against a live Qdrant.

127. [x] [FR-D9/FR-R3] Reconcile purges whose external vector-store delete failed. Completed as `vector_reconcile.py`: admin-only `reconcile_failed_purges` (pending = audit `document.purge` with `vector_store_purge=failed` and no successful `vector_store.purge_retry`), idempotent, bounded to 200 per run, audit with reason code only, no-op for pgvector installs, and `POST /api/v1/admin/vector-store/reconcile-purges`; API reference regenerated (163 paths); see progress_2026-10-05.txt. Follow-up: call it on a schedule from the worker/beat.

128. [x] [FR-O8/FR-I1] Operate and Improve web stages show live data. Completed: `OperateScreen` (AI incidents list) and `ImproveScreen` (flywheel status counts + triage queue) call the admin APIs, map 401/403 to an admin-only notice, EN/ID; web suite 93 passed; see progress_2026-10-05.txt. Follow-up: triage/transition actions, load-more via `next_cursor`, Data/Build stage screens.

129. [x] [FR-D8/FR-B1] Data and Build web stages show live data. Completed: `DataScreen` (documents due for review from `GET /api/v1/documents/reviews/due`) and `BuildScreen` (model registry versions + approval status from `GET /api/v1/model-registry`), 401 -> sign-in notice, other failures -> generic error, EN/ID; web suite 103 passed; see progress_2026-10-05.txt. Follow-up: register/approve actions, load-more via `next_cursor`.

130. [x] [FR-P4/FR-RL2] Release web stage shows live bot approval requests. Completed: `BotReleaseScreen` lists `GET /api/v1/bot-approvals` (type, risk tier, status), 401/403 -> sign-in notice, EN/ID; web suite 107 passed; see progress_2026-10-05.txt. Follow-up: request/decide actions, Test stage (EvalScreen) live data.

131. [x] [FR-T2/NFR-20] Eval runs list API + Test web stage live data. Completed: admin-only cursor-paginated `GET /api/v1/evals/runs` (summaries, no item results) and `EvalScreen` run list, EN/ID; API 17 adjacent tests passed, web 111 passed; see progress_2026-10-05.txt. Follow-up: datasets list, run/new-dataset actions, permission-leak summary.

132. [x] [FR-T1/NFR-20] Eval datasets list API + Test web stage datasets panel. Completed: admin-only cursor-paginated `GET /api/v1/evals/datasets` (summaries, no item contents) and `EvalScreen` dataset list, EN/ID; API 11 adjacent tests passed, web 114 passed; see progress_2026-10-05.txt. Follow-up: run/new-dataset actions, permission-leak summary.

133. [x] [FR-T7/FR-T2] Test stage permission-leak summary derived from the latest `permission-leak.local` run instead of a hardcoded "no leaks" claim; explicit no-run notice, EN/ID. Web suite 118 passed; see progress_2026-10-05.txt.

134. [x] [FR-T1/FR-T2] Test stage actions: New Dataset form (JSON items, validated) and Run Evaluation (ragas.local on newest dataset) wired to `POST /evals/datasets` and `/evals/runs`, lists refresh, generic EN/ID errors. Web suite 124 passed; see progress_2026-10-05.txt.

135. [x] [FR-P4/FR-RL2] Web API contract guard (`api-contract.test.ts`, checks every client endpoint against `docs/openapi.json`) and fix of the Release approvals path (`/governance/bot-approvals`), which would have 404-ed live; see progress_2026-10-05.txt.

136. [x] [FR-P4/FR-RL2] Release stage approve/reject actions on pending bot approvals via `POST /governance/bot-approvals/{id}/decisions`, list refresh, generic EN/ID errors. Web suite 163 passed; see progress_2026-10-05.txt.

137. [x] [FR-I1] Improve stage flywheel triage actions (accept for eval / fine-tuning, dismiss) via `POST /improve/flywheel/{id}/triage`, accept gated on a correction, queue refresh, generic EN/ID errors. Web suite 170 passed; see progress_2026-10-05.txt.

138. [x] [FR-O8] Operate stage incident lifecycle transitions (reported -> released) via `POST /incidents/{id}/transition`, fix notes / release reference required like the API, list refresh, generic EN/ID errors. Web suite 177 passed; see progress_2026-10-05.txt.

139. [x] [FR-D8] Data stage mark-reviewed action with next-review interval via `POST /documents/{id}/lifecycle/reviewed`, due list refresh, generic EN/ID errors. Web suite 182 passed; see progress_2026-10-05.txt.

140. [x] [FR-M7] Build stage model-registry approve/reject actions via `POST /model-registry/{name}/{version}/decision`, approve gated on an eval score like the API, list refresh, generic EN/ID errors. Web suite 188 passed; see progress_2026-10-05.txt.

141. [x] [FR-I1] Improve stage export of accepted flywheel items to a versioned eval/fine-tuning dataset via `POST /improve/flywheel/export`, name required, result and generic EN/ID errors. Web suite 195 passed; see progress_2026-10-05.txt.

### Z. Deferred until external setup / CI-deploy is available
75. [x] [DEFERRED] [FR-RL3] CI integration for eval suites in GitHub Actions / GitLab CI. Deferred per user because current development should not be blocked by workflow permission/CI setup, and this GitHub token lacks `workflow` scope. Saved local backup branch `deferred/fr-rl3-ci-workflow` and patch `C:/Users/riqan/AppData/Local/hermes/cache/scratch/e2eaidev_fr_rl3_ci_deferred.patch`.
76. [x] [DEFERRED] [FR-X3] Real external OAuth provider / token exchange integration. Deferred because it requires an external IdP/OAuth provider setup and credentials; keep the deterministic delegated-identity/token-exchange boundary as the testable local implementation until integration credentials are available.

## Notes
- Items already completed before this file should not be repeated; cron must verify and skip them.
- If an item is too large for one tick, split it into sub-slices and record the sub-slice in `progress_2026-10-05.txt`.
- Keep this backlog updated when a task is completed or split.
