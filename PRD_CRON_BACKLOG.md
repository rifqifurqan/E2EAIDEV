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
4. [FR-T8] OWASP LLM security tests / red-team suites with promptfoo/garak boundaries.
5. [FR-RL2] Release gates: eval thresholds, zero permission leaks, red-team pass, human sign-off.
6. [FR-RL3] CI integration for eval suites in GitHub Actions / GitLab CI.
7. [FR-RL6] Environments: dev -> staging -> prod promotion model, with Lite-tier simplified mode.

### B. Operate / analytics / feedback loop P1
8. [FR-O5] SLOs and alerting: latency, error rate, cost per conversation, guardrail trigger rate.
9. [FR-O6] FinOps: spend per user/team/division/bot, budgets, alerts, chargeback reports.
10. [FR-O7] Usage and ROI analytics: active users, questions per division, answer rate, deflection, unanswered topics, estimated time saved.
11. [FR-I2] Top unanswered questions report for knowledge owners.
12. [FR-B3] Structured-output tests: JSON/schema validity rate per model.

### C. Live tools / MCP / systems integration P1
13. [FR-B4] Live tools through MCP: one MCP server per system generated from OpenAPI.
14. [FR-X2] Live system tools are called at question time through MCP; data is not copied into vectors.
15. [FR-X3] AI acts as the real user using delegated identity/token exchange.
16. [FR-X4] Admin flow to register a system, upload OpenAPI spec, choose endpoints, configure auth, test, and grant roles.
17. [FR-X5] Read-only by default; write actions require explicit confirmation and audit.
18. [FR-X6] Answers combine documents and live data with citations for document pages and system record IDs.

### D. Retrieval/model quality P1
19. [FR-R4] Hybrid search: dense + sparse/BM25 fused with reciprocal rank fusion.
20. [FR-R6] Query rewriting and conversation-aware follow-up questions.
21. [FR-R2] Reranker selectable per bot, including `none`.
22. [FR-M3] Model routing: simple queries to small model, complex to large model, rules/classifier, fallback.
23. [FR-M4] Semantic/prompt caching keyed on permission set.
24. [FR-M2] vLLM serving engine selectable for GPU profile, behind the serving interface.

### E. Data/document P1
25. [FR-D7] Data quality checks: duplicate/near-duplicate detection, stale documents, unparseable files.
26. [FR-D11] Labeling and annotation for gold sets and fine-tuning data.
27. [FR-D15] Optional VLM add-on: routing for figure-heavy/flagged pages, derived output labels, permissions, async enrichment.
28. [FR-D16] Technical/maintenance manuals: procedure-step/figure links, parts/torque/spec tables, verbatim safety warnings.
29. [FR-D4] Complete selectable chunking modes beyond structure-aware: recursive, semantic, parent-child.
30. [FR-C6] Derived content inherits strictest permissions of sources.
31. [FR-C7] Chat history after access revocation hides revoked citations with source-no-longer-accessible notice.

### F. Platform foundation gaps / hardening P0-P1
32. [FR-F8] Tool adapter framework with standard interface and contract tests for every Lab tool.
33. [FR-F20] Job/workflow engine interface: Celery default P0 and Temporal P1 boundary/contract tests.
34. [FR-F4] Install profiles: core, lab-stage, lab-all, GPU/CPU variants for compose/Helm.
35. [FR-F1] OIDC SSO option and identity-provider-down fallback path integration.
36. [FR-F2] Complete Org -> Division -> Team -> User and roles/project scoping gaps; leave SCIM sync for P2.
37. [FR-F7] Harden LiteLLM gateway virtual keys/budgets/fallbacks beyond current baseline.
38. [FR-F11] Finish remaining in-app notification types: review assigned, release approved, incident raised; email stays P2.
39. [FR-F16] Upgrade procedure P2 prep: pre-upgrade backup, health check, rollback notes/tests.
40. [FR-F22] P1 docs: generated OpenAPI/API reference and Lab adapter developer guide.
41. [FR-F21] P1 export from UI for configuration-as-code.

### G. Learning/UI P1
42. [FR-E2] Why-it-matters enterprise panels per lifecycle stage with OWASP/NIST/EU AI Act/ISO/UU PDP links.
43. [FR-F14] Continue WCAG 2.1 AA accessibility hardening beyond existing EN/ID i18n.

### H. P2 compliance / enterprise / connectors after P1 queue
44. [FR-P1] Use-case intake form.
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

## Notes
- Items already completed before this file should not be repeated; cron must verify and skip them.
- If an item is too large for one tick, split it into sub-slices and record the sub-slice in `progress_2026-10-05.txt`.
- Keep this backlog updated when a task is completed or split.
