# E2EAIDEV — Product Requirements Document (PRD)

| | |
|---|---|
| **Product** | E2EAIDEV — End-to-End Enterprise AI Development Lab + Permission-Aware RAG Chatbot |
| **Version** | 1.0 (final draft for review) |
| **Date** | 2026-10-03 |
| **Owner** | rifqifurqan |
| **Status** | Ready for review |
| **Related** | [README.md](README.md): research, tool catalog, and architecture details. **If this PRD and the README disagree, this PRD wins.** |
| **Builders** | Human or AI coding agents: read §17 (build contract) before writing code. |

**Priority key** (maps to the roadmap phases in §13):

| Priority | Phase | Meaning |
|---|---|---|
| **P0** | Phase 0–1 | MVP. Must ship. |
| **P1** | Phase 2 | Lab expansion |
| **P2** | Phase 3 | Enterprise readiness |
| **P3** | Phase 4+ | Advanced |

---

## 1. Summary

Enterprises adopting AI struggle in two ways:

1. **Teams don't understand the full lifecycle.** Prompt engineering, data, retrieval, evaluation, release, monitoring, and governance are each covered by dozens of competing tools. Choices are made from blog posts rather than evidence on the company's own data.
2. **Internal AI assistants either leak or know too little.** A company chatbot must answer from company documents and systems (ERP, HR) while respecting *who is allowed to see what*. Most RAG setups ignore permissions or rely on a single shared knowledge base.

E2EAIDEV solves both:

- **The Lab:** a self-hosted platform covering every stage of the enterprise AI lifecycle. The tools enterprises actually use can be installed side by side and **compared on the company's own data**: quality, agreement with humans, cost, latency, and license. It teaches the lifecycle by doing it.
- **The reference product:** a permission-aware RAG chatbot built and evaluated with the Lab. Users upload and **share documents the way they would in Google Drive** (with a person, team, role, division, or the whole company). Each person's AI only knows what that person may access. The AI can also query existing systems (ERP, HR, CRM) as the asking user.

---

## 2. Goals and non-goals

### 2.1 Goals
| ID | Goal |
|---|---|
| G1 | Cover the whole lifecycle: Plan → Data → Build → Test → Release → Operate → Improve, in one platform. |
| G2 | Let users compare 2–5 enterprise-grade tools per stage on their own data, with fair, reproducible, measured results. |
| G3 | Ship a production-grade, permission-aware RAG chatbot with **zero permission leaks** as a hard release gate. |
| G4 | Connect to existing enterprise systems (ERP, HR, CRM, document stores) without bypassing their permissions. |
| G5 | Run fully self-hosted and air-gapped, on CPU-only hardware (degraded) up to multi-GPU clusters. |
| G6 | Teach: every stage explains *why it matters in enterprise* and links to the relevant standards. |

### 2.2 Non-goals (this version)
- Omnichannel (WhatsApp Business, Slack, Teams, web widget). Planned later as channel adapters (§8.6).
- A multi-tenant SaaS run for many separate companies. One install serves one company.
- Training foundation models from scratch. Only fine-tuning, distillation, and quantization are in scope (P3).
- Replacing ERP/HR systems or writing to them without user confirmation.
- Building our own vector database, inference engine, or evaluation framework. We integrate existing ones.

---

## 3. Users and personas

| Persona | Example | Needs |
|---|---|---|
| **Business user** | Andi, Sales | Ask questions about documents shared with him and about his own ERP/HR data; trust the citations. |
| **Knowledge owner** | A manager uploading a partnership PDF | Upload, organize, and share documents with the right people; know the AI respects that. |
| **AI engineer** | Builds bots | Configure models, prompts, retrieval, and tools; compare options; release versioned bots. |
| **Evaluator / annotator** | QA or domain expert | Review AI answers, label gold sets, calibrate LLM judges. |
| **AI product manager** | Owns a bot | Track quality, adoption, cost, and ROI; approve releases. |
| **Risk / compliance officer** | Legal, security | Classify AI risk, review model cards, audit access and incidents, meet PDP law and EU AI Act obligations. |
| **Platform admin** | IT / infra | Install profiles, manage identity sync, connectors, GPUs, backups, upgrades. |
| **Learner** | New AI team member | Follow guided scenarios to learn the enterprise AI lifecycle hands-on. |

---

## 4. Key user stories

| ID | Story | Priority |
|---|---|---|
| US1 | As a **knowledge owner**, I upload a "WhatsApp Partnership" PDF and share it with Andi (Sales) as viewer, so he can ask the AI about it. | P0 |
| US2 | As **Andi**, I ask "What's the revenue share in the WhatsApp partnership?" and get an answer with a citation to page 4 of the shared PDF. | P0 |
| US3 | As **Budi** (HR, not shared), I ask the same question and the AI reveals nothing from that PDF. | P0 |
| US4 | As a **knowledge owner**, I revoke Andi's access, and his very next question no longer uses that document. | P0 |
| US5 | As **Andi**, I ask "How many leave days do I have?" and the AI queries the HR system **as me** and answers. | P1 |
| US6 | As an **AI engineer**, I run Ragas, DeepEval, Phoenix, and promptfoo on the same dataset and see which agrees best with human labels and at what cost. | P1 |
| US7 | As an **AI engineer**, I compare pgvector vs Qdrant and BGE-M3 vs Qwen3-Embedding on recall@k with Indonesian queries. | P1 |
| US8 | As an **AI PM**, I release bot v1.3 only if evals pass, there are zero permission leaks, red-team tests pass, and I have signed off. I can roll back in one click. | P1 |
| US9 | As a **compliance officer**, I see every AI system, its risk tier, model card, owner, and approval status, and export audit logs to our SIEM. | P2 |
| US10 | As a **platform admin**, I install a CPU-only `core` profile in under 30 minutes on one machine, air-gapped. | P0 (online) / P2 (air-gapped) |
| US11 | As a **learner**, I follow the "Build an HR-policy bot end to end" scenario and understand each lifecycle stage. | P2 |
| US12 | As an **AI PM**, thumbs-down answers flow into an eval dataset so the next release fixes them. | P2 |

---

## 5. Functional requirements: platform foundations

| ID | Requirement | Priority |
|---|---|---|
| FR-F1 | SSO via OIDC (Keycloak bundled as an option; Azure AD and Google Workspace supported). | P0 |
| FR-F2 | Org model: Organization → Division → Team → User, with roles. Manual management in P0; SCIM sync from the HR system or identity provider in P2. | P0 / P2 |
| FR-F2a | **Bootstrap admin:** the install wizard creates one local break-glass admin account (strong generated password, shown once, MFA required in P2). It works before SSO is configured and when the identity provider is down. Every use is audited. | P0 |
| FR-F3 | Platform RBAC with roles Admin, AI Engineer, Evaluator, Compliance, Business User. Roles apply org-wide or per **Project**. A Project is a container for Lab work (datasets, eval suites and runs, bot bundles, comparison reports), owned by a team or division. Document access is **not** governed by Projects; it uses folder/document sharing (§7.1). | P0 |
| FR-F15 | Default limits, admin-configurable: max upload 100 MB per file, 50 files per batch, 20 GB storage per user. Full quotas arrive with FR-F13. | P0 |
| FR-F16 | **Upgrades and migrations:**<br>• Versioned, reversible database schema migrations from the first schema (P0).<br>• Upgrade procedure (P2): pre-upgrade backup → migrations → health check → automatic rollback on failure.<br>• Release notes flag breaking changes.<br>• Upgrades skip at most one minor version; the upgrade path is tested in CI. | P0 (migrations) / P2 (upgrade procedure) |
| FR-F17 | **Secret and certificate rotation:**<br>• Rotate gateway keys, API keys, OIDC client secrets, and database credentials without downtime.<br>• TLS certificates auto-renew (ACME, or the internal CA for air-gapped installs) and alert 14 days before expiry.<br>• Emergency revocation of a leaked key takes effect within 5 minutes. | P2 |
| FR-F4 | Install profiles: `core`, `lab-<stage>`, `lab-all`, plus GPU/CPU variants, through Docker Compose profiles and Helm values. | P0 |
| FR-F5 | Install wizard (CLI first, UI later): detect hardware (CPU, RAM, GPU and VRAM, disk) → recommend a profile → choose tools → **choose models** (FR-F5a) → generate config → pull pinned images → download models. | P0 (CLI) / P2 (UI) |
| FR-F5a | **Model selection is the user's choice.** The platform ships no hardcoded default model. For each role (chat LLM, embedding, reranker, judge, safety classifier), the wizard shows a curated catalog filtered by what fits the detected hardware. Each entry shows size, quantization, estimated RAM/VRAM, expected speed, languages (including Indonesian), license, and a "recommended for your hardware" badge. Users can pick several models per role (for Lab comparisons) or point to an external API through the gateway. Choices can be changed later in Admin → Models without reinstalling. | P0 |
| FR-F5b | Model compatibility check: warn or block when a chosen model won't fit memory, has a non-commercial or restrictive license, or the chosen serving engine doesn't support it (e.g., vLLM on a 6 GB GPU). | P0 |
| FR-F6 | Air-gapped install bundle: image tarballs, a model mirror, offline documentation. | P2 |
| FR-F7 | Model gateway (LiteLLM): one OpenAI-compatible endpoint for Ollama, vLLM, and external APIs, with virtual keys, budgets, and fallbacks. | P0 |
| FR-F8 | Tool adapter framework: a standard interface plus contract tests for every Lab tool; each tool runs in its own container. | P0 |
| FR-F9 | Audit log of every login, upload, share, permission change, query, tool call, release, and admin action. Tamper-evident. | P0 |
| FR-F10 | Audit log export to a SIEM (syslog, OpenTelemetry logs, webhook). | P2 |
| FR-F11 | Notifications (in-app plus email): document shared with you, review assigned, release approved, incident raised. | P0 (in-app) / P2 (email) |
| FR-F12 | Public REST API + Python/TypeScript SDK covering chat, documents, sharing, evals, and bots, with API keys scoped by role. | P1 |
| FR-F13 | Rate limits and quotas per user, team, and division (requests, tokens, storage). | P1 |
| FR-F14 | UI in Indonesian and English (i18n); WCAG 2.1 AA accessibility for chat and document screens. | P0 (EN+ID) / P2 (WCAG) |

---

## 6. Functional requirements: the Lab, by lifecycle stage

Every Lab stage follows **compare mode**:
1. Choose the installed tools.
2. Fix the inputs (same data, same judge or model, same settings).
3. Run them through the adapters.
4. Get a normalized report: measured results (quality, human agreement, latency, cost, variance) next to documented ones (the real metric definitions and judge prompts, license, maturity, operational weight).
5. Read the "why it matters in enterprise" notes.

| ID | Requirement | Priority |
|---|---|---|
| FR-L1 | Compare mode, reusable across all stages. | P1 |
| FR-L2 | Comparison reports are saved, versioned, exportable (PDF/CSV), and shareable. | P1 |
| FR-L3 | Tool catalog page: every tool with its license, maturity, resource needs, and installed/available status. **License warnings** for AGPL, ELv2, and non-commercial licenses. | P1 |

### 6.1 Plan and govern
| ID | Requirement | Priority |
|---|---|---|
| FR-P1 | Use-case intake form: problem, users, success metrics (task success, deflection, time saved), data sources, systems to integrate. | P2 |
| FR-P2 | AI risk classification per bot: EU AI Act tier, NIST AI RMF profile, and Indonesia PDP Law (UU PDP No. 27/2022) data impact. The tier decides the required release gates. | P2 |
| FR-P3 | AI inventory: every model and bot with owner, risk tier, status, **model card**, and **system card**. | P2 |
| FR-P4 | Approval workflow: a high-risk bot needs compliance sign-off before release. | P2 |

### 6.2 Data
| ID | Requirement | Tools (✅ = default) | Priority |
|---|---|---|---|
| FR-D1 | Upload files (PDF, DOCX, PPTX, XLSX, TXT, MD, HTML, images) into folders/spaces, with document versioning. | — | P0 |
| FR-D2 | S3-compatible object storage. | SeaweedFS ✅, Garage, RustFS, Ceph, external S3 | P0 |
| FR-D3 | Parsing with tables, headings, and page anchors for citations. | Docling ✅, Unstructured, MinerU (GPU) | P0 (Docling) / P2 (lab) |
| FR-D4 | Selectable chunking: structure-aware ✅, recursive, semantic, parent-child. | — | P0 (1) / P1 (all) |
| FR-D5 | **Sensitivity labels** (Public / Internal / Confidential / Restricted), set manually or suggested automatically. Labels limit sharing (e.g., Restricted can't be shared company-wide). | — | P1 |
| FR-D6 | PII discovery and optional redaction on ingest. | Presidio ✅ | P1 |
| FR-D7 | Data quality checks: duplicate detection, near-duplicates, stale documents (no review in N months), unparseable files. | — | P1 |
| FR-D8 | Document lifecycle: review owner, review date, expiry; expired documents are excluded from retrieval or flagged. | — | P2 |
| FR-D9 | **Deletion propagation:** deleting a document removes its chunks, embeddings, cache entries, and derived content within 5 minutes. | — | P0 |
| FR-D10 | Dataset versioning and lineage: every index version records its source documents, parser, chunker, and embedding model. | lakeFS / DVC | P2 |
| FR-D11 | Labeling and annotation for gold sets and fine-tuning data. | built-in ✅, Label Studio, Argilla | P1 |
| FR-D12 | Synthetic test-data generation: Q&A pairs, adversarial questions, personas. | Ragas ✅, DeepEval Synthesizer | P0 |
| FR-D13 | Legal hold: documents and chats under hold can't be deleted, overriding retention policy. | — | P2 |

### 6.3 Build: models and serving
| ID | Requirement | Tools | Priority |
|---|---|---|---|
| FR-M1 | Register model endpoints (local or external) through the gateway; test them in a playground. | LiteLLM ✅, Portkey, Kong AI | P0 |
| FR-M2 | Serving engines selectable per install. | Ollama ✅ (CPU), vLLM ✅ (GPU), SGLang, TensorRT-LLM | P0 (Ollama) / P1 (vLLM) / P3 (others) |
| FR-M3 | **Model routing:** send simple queries to a small model and complex ones to a large model, by rule or classifier, with fallbacks. | LiteLLM routing | P1 |
| FR-M4 | Semantic and prompt caching, **keyed on permission set**. | LiteLLM cache / Redis | P1 |
| FR-M5 | Quantization lab: compare AWQ / GPTQ / GGUF on quality loss, speed, and memory. | — | P3 |
| FR-M6 | Fine-tuning and distillation (LoRA/QLoRA, DPO) with results fed back into benchmarking. | Unsloth, Axolotl, TRL | P3 |
| FR-M7 | Model registry with lineage, eval scores, approval status. | MLflow | P2 |
| FR-M8 | Model file security: safetensors preferred, pickle scanning, checksum and signature verification. | — | P2 |

### 6.4 Build: retrieval
| ID | Requirement | Tools | Priority |
|---|---|---|---|
| FR-R1 | Embedding model selectable per knowledge index, from the models installed through the wizard (FR-F5a). Changing the model triggers a versioned re-index job. | Catalog: BGE-M3, Qwen3-Embedding, jina-v3, e5, API models | P0 |
| FR-R2 | Reranker selectable per bot, from the installed models, including "none". | Catalog: bge-reranker-v2-m3, Qwen3-Reranker, Cohere/Jina API | P0 |
| FR-R3 | Vector store selectable per install, behind a `VectorStore` interface. | pgvector ✅, Qdrant, Weaviate, Milvus | P0 (pgvector) / P1 (Qdrant) / P2 (others) |
| FR-R4 | Hybrid search: dense + sparse/BM25, fused with reciprocal rank fusion (RRF). | — | P0 |
| FR-R5 | **Permission-filtered retrieval inside the query** (see §7.2). | OpenFGA ✅, SpiceDB | P0 |
| FR-R6 | Query rewriting and conversation-aware follow-up questions. | — | P0 |
| FR-R7 | Citations with document, page, and section; click through to the source with the passage highlighted. | — | P0 |
| FR-R8 | Retrieval metrics: recall@k, MRR, nDCG, with a separate **Indonesian** evaluation set. | — | P1 |
| FR-R9 | Advanced RAG: GraphRAG, multimodal (images and charts), routing across knowledge bases. | — | P3 |

### 6.5 Build: prompts, conversation, tools, agents
| ID | Requirement | Tools | Priority |
|---|---|---|---|
| FR-B1 | Prompt registry with versions, labels (production/staging), playground, diffs. | Langfuse ✅, MLflow | P0 |
| FR-B2 | **Conversation memory:** short-term (within a session) and optional long-term user memory, which the user can view and delete. | — | P0 (short) / P2 (long) |
| FR-B3 | Structured-output tests: JSON/schema validity rate per model. | native ✅, Guardrails AI, guided decoding | P1 |
| FR-B4 | Live tools through MCP: one MCP server per system, generated from OpenAPI (see §8). | MCP ✅ | P1 |
| FR-B5 | Agent workflows (multi-step, tool chains) with agent-trajectory evaluation. | LangGraph | P3 |

### 6.6 Test: the Eval Lab
| ID | Requirement | Tools | Priority |
|---|---|---|---|
| FR-T1 | Datasets: upload CSV/JSONL, generate synthetically, or curate from production traces; versioned. | — | P0 |
| FR-T2 | Evaluation frameworks as isolated adapters. | Ragas ✅, DeepEval, Arize Phoenix, promptfoo, Inspect AI | P0 (Ragas) / P1 (others) |
| FR-T3 | **Fair judging:** one judge model through the gateway, temperature 0, identical inputs for every framework. | — | P1 |
| FR-T4 | Metric transparency: each score is shown next to that framework's metric definition and the judge prompt it actually sends. | — | P1 |
| FR-T5 | Judging modes per suite: LLM-only (with multi-judge majority vote), human-only, hybrid (route to a human on low confidence, judge disagreement, or random audit). | — | P0 (LLM) / P1 (human, hybrid) |
| FR-T6 | **Evaluate the evaluators:** rank frameworks by agreement with human labels (correlation, Cohen's κ), judge cost per 100 items, latency, variance across 3 runs. | — | P1 |
| FR-T7 | **Permission-leak suite:** personas (e.g., Andi/Sales, Budi/HR, an intern) probe documents they shouldn't access; target is zero leaks. | built-in ✅ | P0 |
| FR-T8 | Security tests to the OWASP Top 10 for LLM Applications, including indirect prompt injection through uploaded documents and data exfiltration. | promptfoo ✅, garak | P1 |
| FR-T9 | Bias and fairness tests across personas, demographics, and languages. | DeepEval bias, custom sets | P2 |
| FR-T10 | Load tests on model endpoints and the full chat API. | guidellm/LLMPerf, k6 ✅, Locust | P2 |
| FR-T11 | Benchmark runner: model × prompt × dataset leaderboard with quality, p50/p95 latency, time to first token, tokens/s, cost. | built-in ✅, lm-evaluation-harness | P1 |
| FR-T12 | Run-vs-run comparison with regression highlighting. | — | P0 |

### 6.7 Release
| ID | Requirement | Priority |
|---|---|---|
| FR-RL1 | **The bot as a versioned bundle:** prompt version + model + index version + reranker + guardrails + tools + config. It is released and rolled back as one unit. | P0 |
| FR-RL2 | Release gates, configurable per risk tier: eval thresholds, zero permission leaks, red-team pass, human sign-off. | P1 |
| FR-RL3 | CI integration: run eval suites from GitHub Actions / GitLab CI and fail the pipeline on regression. | P1 |
| FR-RL4 | Rollout strategies: shadow deploy, canary (traffic %), online A/B test with feature flags. | P2 |
| FR-RL5 | One-click rollback to any previous bundle version. | P1 |
| FR-RL6 | **Environments: dev → staging → prod.** A bot bundle is promoted between environments, never edited in place in prod. Each environment has its own knowledge index, gateway keys, and budgets. Staging uses test or anonymized documents unless an admin explicitly allows production data. Promotion requires that environment's release gates. Single-node installs may run all three as namespaces on one machine. | P1 |

### 6.8 Operate
| ID | Requirement | Tools | Priority |
|---|---|---|---|
| FR-O1 | Traces for every chat: retrieval results, prompt, model, tokens, cost, latency, tool calls. | Langfuse ✅, Phoenix, MLflow 3 | P0 |
| FR-O2 | User feedback: thumbs up/down with an optional correction, attached to the trace. | — | P0 |
| FR-O3 | Online evaluation on sampled production traffic. | Langfuse evaluators | P2 |
| FR-O4 | Drift detection: shifts in query topics, embedding drift, quality decay. | — | P2 |
| FR-O5 | SLOs and alerting: latency, error rate, cost per conversation, guardrail trigger rate. | OpenTelemetry → Prometheus/Grafana ✅ | P1 |
| FR-O6 | FinOps: spend per user, team, division, and bot; budgets, alerts, chargeback reports. | LiteLLM spend | P1 |
| FR-O7 | **Usage and ROI analytics:** active users, questions per division, answer rate, deflection, top unanswered topics, estimated time saved. | — | P1 |
| FR-O8 | AI incident management: report → severity → linked traces → fix → release, with a post-incident record. | — | P2 |
| FR-O9 | Guardrails at runtime: PII redaction, prompt-injection detection, safety classification, output validation. | NeMo Guardrails ✅, Llama Guard 3 ✅, Guardrails AI | P1 |
| FR-O10 | GPU scheduling and sharing. | Kubernetes Kueue, NVIDIA MIG/time-slicing | P3 |
| FR-O11 | Explainability: "Why this answer?" shows the retrieved passages, their scores, the documents considered, and which tools were called. | — | P1 |
| FR-O12 | **PII masking in traces and logs:**<br>• Prompts, retrieved passages, answers, and tool payloads are masked before reaching Langfuse, app logs, or the SIEM. Masked items: names, IDs (e.g., NIK), phone numbers, emails, account numbers, plus custom patterns.<br>• Unmasked trace access is a separate permission, time-limited and audited.<br>• Until masking ships, trace retention defaults to 30 days. | Presidio ✅ | P1 |
| FR-O13 | **Operational runbooks** in `docs/runbooks/`, each with symptoms → diagnosis commands → fix → verification. Minimum set:<br>• service down / restart<br>• restore from backup<br>• GPU out of memory<br>• model endpoint failing or slow<br>• vector store degraded<br>• permission-sync (SCIM/OpenFGA) lag<br>• disk full<br>• leaked key<br>Each runbook is exercised at least once in a staging drill before GA. | — | P2 |

### 6.9 Improve
| ID | Requirement | Priority |
|---|---|---|
| FR-I1 | **Data flywheel:** flagged answers (thumbs-down, low online score, reviewer flag) → triage queue → added to an eval dataset or fine-tuning set → re-evaluated → new bundle released. | P2 |
| FR-I2 | "Top unanswered questions" report that tells knowledge owners which documents are missing. | P1 |

### 6.10 Learning layer
| ID | Requirement | Priority |
|---|---|---|
| FR-E1 | Navigation follows the lifecycle (Plan → Data → Build → Test → Release → Operate → Improve). | P0 |
| FR-E2 | A "Why it matters in enterprise" panel per stage, linking to OWASP, NIST AI RMF, EU AI Act, ISO/IEC 42001, and UU PDP. | P1 |
| FR-E3 | Guided scenarios with sample data and expected outcomes (e.g., HR-policy bot; "Why does my bot hallucinate?"; "Find the permission leak"). | P2 |
| FR-E4 | Role-based learning paths (AI engineer, evaluator, AI PM, compliance, platform). | P3 |

---

## 7. Functional requirements: reference product (permission-aware RAG chatbot)

### 7.1 Document sharing ("Google Drive for knowledge")
| ID | Requirement | Priority |
|---|---|---|
| FR-S1 | Share a document or folder with a **user, team, role, division, or the whole company**. | P0 |
| FR-S2 | Permission levels: **Owner** (share, delete), **Editor** (replace, re-upload), **Viewer** (read, ask the AI). | P0 |
| FR-S3 | Folder and space inheritance: sharing a folder shares its contents; explicit sharing on a document adds to it. | P0 |
| FR-S4 | Share expiry date (for temporary project teams). | P1 |
| FR-S5 | Access requests: a user can request access, and the owner approves or denies. | P1 |
| FR-S6 | "Shared with me", "My documents", and "My team" views; the share dialog shows who currently has access. | P0 |
| FR-S7 | Sharing is limited by sensitivity label (FR-D5) and an admin policy (e.g., no external sharing, no company-wide sharing for Confidential). | P1 |
| FR-S8 | Access changes follow org changes automatically: someone who moves divisions loses or gains access through SCIM sync. | P2 |
| FR-S9 | Implementation: relationship-based access control (Zanzibar model) with OpenFGA ✅; SpiceDB as the Lab alternative. | P0 |

### 7.2 Permission-aware chat
| ID | Requirement | Priority |
|---|---|---|
| FR-C1 | **Index once, filter at query time.** Embeddings are never copied per user. Sharing or revoking never triggers re-embedding. | P0 |
| FR-C2 | Retrieval is filtered by permission **inside the vector query**, never by removing results after top-k retrieval. | P0 |
| FR-C3 | Chat scopes: this document only / my documents / shared with me / my team / everything I can access. | P0 |
| FR-C4 | Revoked access takes effect on the user's **next query** (≤ 5 s). | P0 |
| FR-C5 | Caches are keyed on the user's permission set; no answer is served across permission boundaries. | P0 |
| FR-C6 | Derived content (summaries, knowledge graphs, insights) inherits the **strictest** permissions of its sources. | P1 |
| FR-C7 | Chat history after access is revoked: citations from revoked sources are hidden and replaced with a "source no longer accessible" notice. | P1 |
| FR-C8 | Retrieved text is treated as untrusted data: documents are scanned on upload and guardrails run on retrieved context. | P1 |
| FR-C9 | Streaming answers with citations, copy/export, feedback, and "Why this answer?" (FR-O11). | P0 |
| FR-C10 | Notification when something is shared with you: "X shared Y with you — ask the AI about it." | P0 |

### 7.3 Enterprise system connections
| ID | Requirement | Priority |
|---|---|---|
| FR-X1 | **Knowledge connectors** sync documents and **mirror the source system's permissions**: Google Drive, SharePoint/OneDrive, Nextcloud (WebDAV), Confluence. | P2 |
| FR-X2 | **Live system tools** (ERP, HR, CRM) are called at question time through MCP. This data isn't copied into vectors. | P1 |
| FR-X3 | **The AI acts as the real user:** it calls system APIs with the asking user's identity (OAuth token exchange or a per-user delegated token). A super-admin service account is never used for user data. | P1 |
| FR-X4 | Admin flow: register a system → upload its OpenAPI spec → choose allowed endpoints → configure auth → test in the playground → grant to roles or divisions. | P1 |
| FR-X5 | Read-only by default. Write actions (e.g., submit a leave request) require explicit user confirmation and are written to the audit log. | P1 (read) / P3 (write) |
| FR-X6 | Answers can combine documents and live data, with citations for both (document page + system record ID). | P1 |
| FR-X7 | Ready-made connector templates for common Indonesian and global systems (e.g., SAP, Odoo, Talenta/Mekari, Salesforce). Final list to be decided (§15). | P2 |

### 7.4 Later: omnichannel (not in this version)
- WhatsApp Business, Slack, Teams, and an embeddable web widget, each built as a channel adapter on the public chat API (FR-F12).
- Each channel must link the channel account (phone number, Slack ID) to an employee identity, so permissions apply in every channel.

---

## 8. Non-functional requirements

Targets are for the reference hardware (§12) and must be validated in Phase 1–2 load tests.

| ID | Category | Requirement |
|---|---|---|
| NFR-1 | Performance | Chat time to first token, p95: **≤ 3 s** (GPU profile, 8B model) / **≤ 8 s** (CPU profile, ≤ 4B quantized model). |
| NFR-2 | Performance | Permission-filtered hybrid retrieval with rerank, p95: **≤ 800 ms** at 1M chunks. |
| NFR-3 | Performance | Ingestion: **≥ 20 pages/min** on CPU and **≥ 100 pages/min** on GPU (Docling). |
| NFR-4 | Scalability | GPU reference profile supports **≥ 200 concurrent chat users**. Scales horizontally on Kubernetes. pgvector up to ~20M chunks; Qdrant beyond that. |
| NFR-5 | Availability | Single node: best effort, with backups. HA profile (Kubernetes): **99.9%** monthly for the chat API. |
| NFR-6 | Durability | Daily backups of Postgres, vector store, object storage, OpenFGA, and Langfuse (ClickHouse traces). Restore tested quarterly. RPO ≤ 24 h, RTO ≤ 4 h (single node); RPO ≤ 1 h (HA). |
| NFR-7 | Security | TLS everywhere; encryption at rest; secrets in Vault or Kubernetes secrets; no plaintext credentials in the database or logs. |
| NFR-8 | Security | Permission correctness: **0 leaks** in the leak suite is a release gate. Access changes apply in ≤ 5 s. |
| NFR-9 | Security | Supply chain: pinned image digests, hash-locked dependencies, SBOM per release, dependency and container scanning in CI, signed release artifacts. |
| NFR-10 | Privacy and compliance | Configurable retention for chats, traces, and documents. Data-subject requests (export or delete a person's data). Legal hold. Data stays on premises by default. Supports UU PDP No. 27/2022 obligations; GDPR-ready. |
| NFR-11 | Auditability | Every access-relevant action is audited, immutable, kept ≥ 1 year (configurable), and exportable to a SIEM. |
| NFR-12 | Portability | Runs on Linux x86_64 with Docker Compose or Kubernetes 1.29+. Works fully air-gapped. NVIDIA GPU optional. |
| NFR-13 | Usability | Indonesian + English UI. A new business user can ask a first question within 2 minutes of logging in, with no training. |
| NFR-14 | Accessibility | WCAG 2.1 AA for the chat, documents, and sharing screens. |
| NFR-15 | Maintainability | Every Lab adapter has contract tests and a nightly smoke test. Tool versions are pinned and upgraded deliberately. |
| NFR-16 | Observability | All services emit OpenTelemetry traces, metrics, and logs. Each LLM call has a trace ID shown to admins and linked from feedback. |
| NFR-17 | Licensing | Platform code is under a permissive open-source license (proposed: Apache 2.0). AGPL tools run as separate services only. The license of every tool and model is shown before install. |

---

## 9. Success metrics

| Area | Metric | Target (first 6 months after GA) |
|---|---|---|
| Safety | Permission leaks in production and the leak suite | **0** |
| Quality | Faithfulness (judge calibrated against humans) on gold sets | ≥ 0.85 |
| Quality | Answer rate (questions answered with ≥ 1 valid citation) | ≥ 80% |
| Quality | Thumbs-up rate | ≥ 75% |
| Evaluation | LLM-judge agreement with humans (Cohen's κ) | ≥ 0.6 |
| Adoption | Weekly active users / licensed users | ≥ 40% |
| Adoption | Documents shared per active knowledge owner per month | ≥ 3 |
| Efficiency | Median cost per answered question | Tracked; ≥ 30% lower after model routing and caching |
| Lab | Stages with ≥ 2 comparable tools installed and reported | 7 of 7 lifecycle stages by end of Phase 3 |
| Platform | `core` install time on reference CPU hardware | ≤ 30 min |
| Learning | Learners completing at least one guided scenario | ≥ 70% of those who start |

---

## 10. Technology decisions (summary)

Full research and comparisons are in [README.md §3](README.md).

| Layer | Default | Lab alternatives |
|---|---|---|
| API / UI | FastAPI (Python 3.12) / Next.js (TypeScript) | — |
| System of record | PostgreSQL | — |
| Queue / cache | Redis | — |
| Identity / SSO | OIDC (Keycloak bundled optional), SCIM | Azure AD, Google Workspace |
| Document authorization | OpenFGA | SpiceDB |
| Model gateway | LiteLLM (pinned, digest-verified) | Portkey, Kong AI |
| Serving | Ollama (CPU), vLLM (GPU) | SGLang, TensorRT-LLM |
| Object storage | SeaweedFS | Garage, RustFS, Ceph, external S3 |
| Parsing | Docling | Unstructured, MinerU |
| Chat LLM | *User's choice in the wizard* (FR-F5a) | Catalog: Qwen3, Llama, Gemma, Mistral families (quantized variants), external APIs |
| Embeddings | *User's choice in the wizard*; BGE-M3 is often recommended | Catalog: Qwen3-Embedding, jina-v3, e5, APIs |
| Reranker | *User's choice in the wizard*; bge-reranker-v2-m3 is often recommended | Catalog: Qwen3-Reranker, APIs, none |
| Vector store | pgvector | Qdrant, Weaviate, Milvus |
| Prompts / traces | Langfuse | Phoenix, MLflow 3 |
| Evaluation | Ragas | DeepEval, Phoenix, promptfoo, Inspect AI |
| Guardrails | NeMo Guardrails + Llama Guard 3 | Guardrails AI |
| Red-teaming | promptfoo | garak |
| PII | Presidio | GLiNER-based |
| Live tools | MCP servers (OpenAPI → MCP) | — |
| Infra observability | OpenTelemetry → Prometheus + Grafana | — |
| Model registry | MLflow | — |
| Data versioning | lakeFS | DVC |

**Excluded on purpose:**
- MinIO CE: archived in 2026.
- TGI: archived in 2026.
- LLM Guard: archived in July 2026.
- NV-Embed-v2: non-commercial license.
- Dify as a base: its license restricts multi-tenant use.

---

## 11. Assumptions and dependencies

- The customer has an identity provider or HR system that can export org structure (SCIM, an API, or CSV for the first version).
- ERP/HR/CRM systems expose REST APIs with per-user authentication (OAuth2/OIDC or delegated tokens). Systems without this need a custom adapter.
- Local models are used under their own licenses (e.g., Llama community license, Apache 2.0 Qwen). The customer accepts these at install time.
- Indonesian-language quality depends on the chosen models. The Lab measures it; it isn't guaranteed.

---

## 12. Reference hardware (for sizing and NFR targets)

| Profile | Hardware | Intended use |
|---|---|---|
| **CPU-lite** | 16 vCPU, 64 GB RAM, 500 GB SSD, no GPU | Pilot, learning, ≤ 30 concurrent users, quantized models ≤ 4B |
| **GPU-standard** | 32 vCPU, 128 GB RAM, 1 TB NVMe, 1× 48–80 GB GPU (e.g., L40S / A100 / H100) | Department production, ≤ 200 concurrent users, 8B–32B models |
| **Enterprise HA** | Kubernetes, 3+ nodes, GPU node pool | Company-wide, 99.9% availability |

---

## 13. Release plan

| Phase | Duration | Scope | Exit criteria |
|---|---|---|---|
| **0: Foundations** | ~2 wks | Monorepo, CI, pinned dependencies; `core` profile (Postgres, Redis, LiteLLM, SeaweedFS, Langfuse, Ollama, OpenFGA); OIDC; org model; adapter framework; audit log; **CLI install wizard with hardware detection and model selection** | The wizard detects hardware, the user picks models, and the `core` profile comes up healthy; login works; the chosen model answers through the gateway |
| **1: MVP** | ~8 wks | All P0: upload/parse/chunk/embed, sharing, permission-aware chat with citations and scopes, bot bundles, Ragas evals, leak suite, feedback, traces, EN/ID UI | US1–US4 pass on CPU-lite; **0 leaks**; NFR-1/2 met for CPU; an eval report is produced |
| **2: Lab** | ~6 wks | All P1: Eval Lab (DeepEval, Phoenix, promptfoo, hybrid judging, evaluate-the-evaluators), Retrieval Lab, vLLM, benchmark runner, live tools v1 (read-only), release gates and CI, guardrails, model routing, FinOps, ROI analytics, public API/SDK | US5–US8 pass; comparison reports for evaluation, retrieval, and serving; GPU NFRs met |
| **3: Enterprise** | ~6–8 wks | All P2: knowledge connectors with permission mirroring, SCIM, governance (inventory, risk tiers, cards, approvals), lineage, legal hold, rollouts, online evals, drift, incidents, flywheel, Helm, air-gapped bundle, backup and disaster recovery, SIEM export, WCAG, guided scenarios | US9–US12 pass; HA profile meets 99.9% in a soak test; air-gapped install verified |
| **4: Advanced** | ongoing | All P3: fine-tuning, distillation, and quantization labs; agents and write actions; GraphRAG and multimodal; SGLang/TensorRT-LLM; GPU scheduling; learning paths; omnichannel | Per feature |

---

## 14. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Permission leak through retrieval, cache, or derived content | Critical | Filtering inside the query, permission-keyed caches, strictest-permission inheritance, leak suite as a release gate, penetration test before GA. |
| Too many tools, so it's heavy and slow to build | High | Light `core` profile; opt-in `lab-*` profiles; adapters added stage by stage; contract tests. |
| Tool API changes break adapters | Medium | Pinned versions, nightly smoke tests, deliberate upgrades. |
| Supply-chain compromise (e.g., the LiteLLM PyPI incident, March 2026) | Critical | Digest-pinned images, hash locks, SBOM, scanning, isolated gateway secrets. |
| LLM-judge bias and drift | Medium | Hybrid judging, human gold sets, κ monitoring. |
| Weak Indonesian retrieval or answers | Medium | Indonesian eval set; multilingual models (BGE-M3, Qwen3) by default; measured in the Lab. |
| ERP/HR systems lack per-user auth | Medium | Delegated-token adapter pattern; read-only scoped service accounts with *server-side* user filtering as a documented, audited fallback. |
| License problems (AGPL, ELv2, non-commercial) | Medium | License shown and checked at install; AGPL tools run as separate services. |
| Langfuse (ClickHouse) too heavy for CPU-lite | Low | Measure; Postgres-only tracing fallback. |
| CPU-only installs perform poorly | Medium | Quantized small models, model routing, a clear hardware sizing guide. |

---

## 15. Open questions

| # | Question | Owner | Needed by |
|---|---|---|---|
| Q1 | Which ERP/HR/CRM systems come first (SAP, Odoo, Talenta/Mekari, Salesforce, internal APIs)? | Product | Phase 2 start |
| Q2 | Which identity providers do target customers use (Azure AD, Google Workspace, Keycloak, LDAP)? | Product | Phase 0 |
| Q3 | Final open-source license for the platform (Apache 2.0 proposed)? | Owner | Phase 0 |
| ~~Q4~~ | ~~Default local LLM?~~ **Resolved:** no hardcoded default. The user chooses models in the install wizard from a hardware-filtered, license-checked catalog (FR-F5a). Remaining work: curate the initial catalog. | AI eng | Phase 0 |
| Q5 | Is external sharing (people outside the company, e.g., partners) needed? If yes, which phase? | Product | Phase 1 |
| Q6 | Should OCR for scanned documents (MinerU, GPU) be in the MVP for target customers? | Product | Phase 1 |
| Q7 | Will there be a hosted demo / training environment? | Owner | Phase 3 |

---

**Defaults if a question is still open when its phase starts.** Builders use these and log them in the Decisions section of `AGENTS.md`:
- **Q2:** Keycloak, bundled, as the OIDC provider. Other providers connect to Keycloak or directly through OIDC later.
- **Q3:** Apache 2.0.
- **Q5:** No external sharing in the MVP. The sharing model must not rule it out later (keep a "guest" principal type in the OpenFGA model).
- **Q6:** No MinerU in the MVP. Scanned PDFs use Docling's built-in CPU OCR, flagged as "low-confidence parse."

---

## 16. Glossary

| Term | Meaning |
|---|---|
| **RAG** | Retrieval-Augmented Generation: the AI answers using passages retrieved from documents. |
| **Reranker** | A model that re-orders retrieved passages by relevance before the LLM sees them. |
| **ReBAC / Zanzibar** | Relationship-based access control; the model behind Google Drive sharing, implemented by OpenFGA and SpiceDB. |
| **LLM-as-a-judge** | Using an LLM to score another model's answers against a rubric. |
| **Cohen's κ** | A statistic for agreement between two raters (e.g., LLM judge vs human) that corrects for chance. |
| **MCP** | Model Context Protocol: the standard way to expose tools and APIs to LLMs. |
| **Bot bundle** | A versioned set of prompt, model, index, reranker, guardrails, and tools, released as one unit. |
| **Shadow deploy** | A new version answers silently next to the live one, so they can be compared without affecting users. |
| **SCIM** | A standard protocol for syncing users and groups from an identity provider. |
| **UU PDP** | Indonesia's Personal Data Protection Law (Law No. 27 of 2022). |
| **Air-gapped** | Runs with no internet connection. |

---

## 17. Build contract (for human and AI builders)

This section defines *how* the product is built. It binds every builder, including AI coding agents working across many sessions.

### 17.1 Build order
- Build strictly **Phase 0 → 1 → 2 → 3 → 4**. Don't start a phase until the previous phase's exit criteria (§13) pass with `make verify-phase-N`.
- Within a phase, build only that phase's priority (P0 for Phase 0–1, P1 for Phase 2, and so on). The non-goals in §2.2 limit the product; this rule also limits *timing*. Don't build later-phase features early, even partially.
- Build thin end-to-end slices before going wide. Phase 1's first slice: upload PDF → parse → embed → share with Andi → Andi gets a cited answer → Budi gets nothing.

### 17.2 Repository layout
```
apps/api/             FastAPI service (Python 3.12, managed with uv)
apps/web/             Next.js app (TypeScript, pnpm)
workers/              ingestion, eval, and benchmark workers (Redis-backed task queue; Celery by default)
adapters/<stage>/<tool>/   one Lab tool per folder: Dockerfile, adapter code, contract test
cli/                  install wizard (Python, Typer) — FR-F5
catalog/models.yaml   model catalog: role, size, quantization, RAM/VRAM, languages, license, engines
catalog/tools.yaml    tool catalog: stage, license, maturity, resources, profile
deploy/compose/       Docker Compose files with profiles (core, lab-*, gpu)
deploy/helm/          Helm chart (Phase 3)
deploy/versions.lock  resolved image digests and package versions (see 17.6)
packages/sdk-python/, packages/sdk-ts/   public SDKs (Phase 2)
tests/e2e/            user-story acceptance tests (pytest + Playwright)
docs/                 operator and user documentation
```

### 17.3 Executable acceptance
- Each user story has an automated test named after it, for example `tests/e2e/test_us01_share_with_andi.py` and `tests/e2e/test_us03_budi_sees_nothing.py`.
- `make verify-phase-N` brings up the profile, seeds the test org (Org "Demo"; divisions Sales and HR; users Andi in Sales, Budi in HR, an intern), runs that phase's user-story tests plus the permission-leak suite, and exits non-zero on any failure.
- A phase is done only when `make verify-phase-N` passes on the reference CPU-lite machine. "It works on my machine" doesn't count.

### 17.4 Definition of done for each requirement
1. Code plus unit tests; adapters also pass the adapter contract tests.
2. Audit-log events emitted where FR-F9 applies.
3. Permission checks covered by the leak suite where the feature touches documents or chat.
4. User and operator docs updated in `docs/`.
5. The requirement ID (e.g., `FR-S1`) is referenced in the commit message or PR.

### 17.5 Decision policy
- **Builder decides and logs** (in the Decisions section of `AGENTS.md`: date, context, decision, alternatives): reversible implementation choices, such as library choice within the approved stack, internal API shapes, schema details, UI layout.
- **Builder asks the owner first:** anything that changes product scope, contradicts this PRD, changes the security or permission model, introduces a new license class (AGPL, ELv2, non-commercial), adds a paid or external service, or is hard to reverse (data migrations on shared data, public API contracts after Phase 2).

### 17.6 Versions and research re-verification
- At the start of Phase 0, resolve the latest stable version of every component and model in the `core` profile. Record image digests and package versions in `deploy/versions.lock`. Never use `latest` tags or unpinned installs.
- At the start of each phase, re-verify the research claims for the tools that phase introduces: license, maintenance status (archived or active), security incidents, versions. Use primary sources (official repo, release notes, security advisory). If a claim in README §3 turns out wrong, log it in the Decisions section of `AGENTS.md` and propose a replacement before building on it.

### 17.7 Session handoff (multi-session agents)
- `AGENTS.md`: how to set up, run, test, and verify; coding conventions; where things live.
- `AGENTS.md` → **Progress** section: current phase; requirement IDs done, in progress, and blocked; last `verify` result; the next 3 tasks. Update it at the end of every working session.
- `AGENTS.md` → **Decisions** section: the decision log from 17.5, newest first.
- A new session reads, in order: this PRD → `AGENTS.md` (setup, Progress, Decisions), then continues. One file keeps the handoff in one place.

### 17.8 Core screens (Phase 1)
Screens to build. Layout and visual design are the builder's choice, within the lifecycle navigation (FR-E1).

| Screen | Covers |
|---|---|
| App shell | Lifecycle navigation, language switch (EN/ID), notifications |
| Login | OIDC plus the bootstrap admin (FR-F2a) |
| Chat | Scope selector, streaming answers, citations, feedback, model/bot picker |
| Documents | My documents / Shared with me / My team; folders; upload |
| Share dialog | Add a user, team, role, division, or company; set the permission level; see who has access |
| Document viewer | Open a cited passage with highlighting |
| Admin → Org | Divisions, teams, users, roles |
| Admin → Models | Installed models per role, gateway providers, test prompt |
| Eval | Datasets, run an eval, run results, run-vs-run comparison, leak-suite results |
| Bots | Bot bundles, versions, release and rollback |
