# E2EAIDEV — Product Requirements Document (PRD)

| | |
|---|---|
| **Product** | E2EAIDEV — End-to-End Enterprise AI Development Lab + Permission-Aware RAG Chatbot |
| **Version** | 1.5 |
| **Date** | 2026-10-04 |
| **Owner** | rifqifurqan |
| **Status** | Complete for build. Open owner decisions in §15 all have defaults, so none of them block Phase 0. |
| **Related** | [README.md](README.md): research, tool catalog, and architecture details. **If this PRD and the README disagree, this PRD wins.** |
| **Builders** | Human or AI coding agents: read §17 (build contract) and **Part II (technical design)** before writing code. |

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
- Omnichannel (WhatsApp Business, Slack, Teams, web widget). Planned later as channel adapters (§7.4).
- Native mobile apps. The web UI is responsive and works in mobile browsers (NFR-13).
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
| US13 | As an **admin**, I deactivate Andi when he leaves the company. His sessions and tokens stop working immediately, and his documents transfer to his manager without breaking existing shares. | P0 |
| US14 | As a **solo developer** with a 16 GB laptop and no server, I pick the Lite tier, skip staging, use Ollama with a small model (or an external API), and still get the full share → ask → cited answer → no-leak flow. | P0 |
| US15 | As a **maintenance technician**, I ask "How do I replace the spindle bearing on line 3's CNC?" and get the steps with the matching diagram, part numbers, torque values from the spec table, and the manual's safety warnings quoted word for word. | P1 |

---

## 5. Functional requirements: platform foundations

| ID | Requirement | Priority |
|---|---|---|
| FR-F1 | SSO via OIDC (Keycloak bundled as an option; Azure AD and Google Workspace supported). | P0 |
| FR-F2 | Org model: Organization → Division → Team → User, with roles. Manual management in P0; SCIM sync from the HR system or identity provider in P2. | P0 / P2 |
| FR-F2a | **Bootstrap admin:** the install wizard creates one local break-glass admin account (strong generated password, shown once, MFA required in P2). It works before SSO is configured and when the identity provider is down. Every use is audited. | P0 |
| FR-F3 | Platform RBAC with roles Admin, AI Engineer, Evaluator, Compliance, Business User. Roles apply org-wide or per **Project**. A Project is a container for Lab work (datasets, eval suites and runs, bot bundles, comparison reports), owned by a team or division. Document access is **not** governed by Projects; it uses folder/document sharing (§7.1). | P0 |
| FR-F4 | Install profiles: `core`, `lab-<stage>`, `lab-all`, plus GPU/CPU variants, through Docker Compose profiles and Helm values. | P0 |
| FR-F19 | **Install tiers: Lite / Standard / Enterprise** (§12), chosen in the wizard. All tiers run the same codebase; a tier only changes which components are installed, through configuration behind existing interfaces. No feature forks, and the permission model is identical in every tier. | P0 (Lite, Standard) / P2 (Enterprise) |
| FR-F20 | **Job / workflow engine, chosen in the wizard: Celery or Temporal.**<br>• Background work (ingestion, Docling parsing, VLM enrichment, re-indexing, connector sync, eval and benchmark runs) is written once against one internal job interface. A setting picks the engine.<br>• **Celery** (default, every tier): light, runs on the existing Redis.<br>• **Temporal** (Standard and Enterprise): durable multi-step workflows that survive restarts, with full run history and a workflow UI. It uses the existing Postgres.<br>• **Both engines:** retries with backoff, idempotent steps, progress shown in the UI, cancel, and the same audit events. The job contract tests run against both engines. | P0 (Celery) / P1 (Temporal) |
| FR-F21 | **Configuration as code:** the whole install (tier, components, models, policies, egress rules, bots) is captured in one validated config file that can be versioned in git, diffed, and re-applied to rebuild an identical install. Invalid config fails at startup with a clear message. Secrets are referenced, never stored in it. | P0 (file + validation) / P1 (export from UI) |
| FR-F22 | **Documentation deliverables** in `docs/`, in English and Indonesian:<br>• user guide<br>• admin and operator guide (install, tiers, upgrades, backups, runbooks)<br>• API reference (generated from OpenAPI)<br>• adapter developer guide (how to add a Lab tool). | P0 (user, admin) / P1 (API, adapter guide) |
| FR-F5 | Install wizard (CLI first, UI later): detect hardware (CPU, RAM, GPU and VRAM, disk) → **recommend a tier** (FR-F19) and profile → choose tools → **choose models** (FR-F5a) → choose the job engine (FR-F20) → generate config → pull pinned images → download models. | P0 (CLI) / P2 (UI) |
| FR-F5a | **Model selection is the user's choice.** The platform ships no hardcoded default model. For each role (chat LLM, embedding, reranker, judge, safety classifier, and optional vision model for FR-D15), the wizard shows a curated catalog filtered by what fits the detected hardware. Each entry shows size, quantization, estimated RAM/VRAM, expected speed, languages (including Indonesian), license, and a "recommended for your hardware" badge. Users can pick several models per role (for Lab comparisons) or point to an external API through the gateway. Choices can be changed later in Admin → Models without reinstalling. | P0 |
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
| FR-F15 | Default limits, admin-configurable: max upload 100 MB per file, 50 files per batch, 20 GB storage per user. Full quotas arrive with FR-F13. | P0 |
| FR-F16 | **Upgrades and migrations:**<br>• Versioned, reversible database schema migrations from the first schema (P0).<br>• Upgrade procedure (P2): pre-upgrade backup → migrations → health check → automatic rollback on failure.<br>• Release notes flag breaking changes.<br>• Upgrades skip at most one minor version; the upgrade path is tested in CI. | P0 (migrations) / P2 (upgrade procedure) |
| FR-F17 | **Secret and certificate rotation:**<br>• Rotate gateway keys, API keys, OIDC client secrets, and database credentials without downtime.<br>• TLS certificates auto-renew (ACME, or the internal CA for air-gapped installs) and alert 14 days before expiry.<br>• Emergency revocation of a leaked key takes effect within 5 minutes. | P2 |
| FR-F18 | **User offboarding:**<br>• Deactivating a user revokes their sessions, API keys, and delegated tokens within 1 minute.<br>• Their owned documents and folders transfer to a chosen owner (default: their manager); existing shares to others stay intact.<br>• Their chats follow the retention policy (NFR-10).<br>• Manual in P0; automatic from SCIM deprovisioning in P2. | P0 / P2 |

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
| FR-L2 | Comparison reports are saved, versioned, exportable (PDF/CSV), and shareable. Every run records tool versions, model versions, configuration, dataset version, and random seeds, so it can be re-run and reproduced. | P1 |
| FR-L4 | Cost and time estimate before a run starts (judge tokens × price, GPU minutes). Runs over a budget threshold need confirmation. | P1 |
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
| FR-D1 | Upload files (PDF, DOCX, PPTX, XLSX, TXT, MD, HTML, images) into folders/spaces, with document versioning. Retrieval uses only the latest version; citations in old chats keep pointing to the version they quoted. | — | P0 |
| FR-D2 | S3-compatible object storage. | SeaweedFS ✅, Garage, RustFS, Ceph, external S3 | P0 |
| FR-D3 | **Baseline document understanding (every tier):**<br>• Layout-aware parsing with headings and page anchors.<br>• **Tables** extracted as structured rows and columns.<br>• **OCR** for scanned pages (CPU), with Indonesian and English language packs by default; more languages are configurable.<br>• **Figures and charts** saved as image crops and indexed with their captions and surrounding text.<br>• Pages with low OCR confidence or complex layout are flagged "low-confidence parse".<br>• Parsing tools: Docling ✅ in P0; Unstructured and MinerU (GPU) as Lab alternatives in P2. | Docling ✅, Unstructured, MinerU (GPU) | P0 (Docling) / P2 (lab) |
| FR-D15 | **Vision model add-on (optional, per install):** a vision-language model (VLM) chosen in the wizard as its own model role (FR-F5a).<br>• **Routing:** only flagged or figure-heavy pages go to the VLM, never every page, so GPU time stays low. Admins can also force VLM parsing for chosen folders (e.g., "Maintenance manuals").<br>• **Outputs:** page-to-structured-text for hard scans; descriptions of figures, diagrams, and schematics; data extracted from charts (series, values, axes). These are indexed next to the text chunks.<br>• **Labeling:** VLM-derived content is marked "AI-described from figure" and shown alongside the original image crop.<br>• **Permissions:** VLM output is derived content and inherits the document's permissions (FR-C6). Egress policy applies when the VLM is an external API (FR-M9).<br>• **Runs asynchronously:** the document is searchable from baseline parsing first, then enriched when the VLM finishes. | Catalog examples, to re-verify per §17.6: Qwen-VL family (Qwen2.5-VL / Qwen3-VL), Granite-Docling, MinerU VLM backend; external vision APIs | P1 |
| FR-D16 | **Technical and maintenance manuals** (e.g., factory machine repair and maintenance PDFs):<br>• Keep the links between procedure steps and the figures they reference ("see Fig. 4-2").<br>• Keep part numbers, torque/spec tables, and exploded-diagram callouts as structured, searchable data.<br>• **Safety warnings** (WARNING / CAUTION / DANGER) attached to a procedure are always included **verbatim** in any answer about that procedure.<br>• Numeric values (torque, pressure, clearance) in answers are quoted from source text or tables when available. Values read only by the VLM from a figure are flagged and shown with the figure crop for the user to confirm. | P1 (requires FR-D15 for figures) |
| FR-D4 | Selectable chunking: structure-aware ✅, recursive, semantic, parent-child. | — | P0 (1) / P1 (all) |
| FR-D5 | **Sensitivity labels** (Public / Internal / Confidential / Restricted), set manually or suggested automatically. Labels limit sharing (e.g., Restricted can't be shared company-wide). | — | P1 |
| FR-D6 | PII discovery and optional redaction on ingest. | Presidio ✅ | P1 |
| FR-D7 | Data quality checks: duplicate detection, near-duplicates, stale documents (no review in N months), unparseable files. | — | P1 |
| FR-D8 | Document lifecycle: review owner, review date, expiry; expired documents are excluded from retrieval or flagged. | — | P2 |
| FR-D9 | **Deletion propagation:**<br>• Deleting a document moves it to **trash**. Within 5 minutes it is excluded from retrieval, caches, and derived content.<br>• The owner can restore it from trash for 30 days (configurable).<br>• After that, or on "delete permanently", its file, chunks, and embeddings are purged.<br>• Legal hold (FR-D13) blocks the purge. | — | P0 |
| FR-D14 | Malware scanning on upload. Infected files are quarantined and never parsed. | ClamAV ✅ (GPL, runs as a separate service) | P1 |
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
| FR-M9 | **Data egress policy:**<br>• External model APIs are **off by default**. Enabling them is an install-wide admin setting with a clear warning (P0).<br>• Per sensitivity label, admins choose allowed destinations; for example, Confidential and Restricted content goes only to local models (P1, with FR-D5).<br>• The gateway enforces the policy, and every blocked call is audited. | LiteLLM routing rules | P0 / P1 |

### 6.4 Build: retrieval
| ID | Requirement | Tools | Priority |
|---|---|---|---|
| FR-R1 | Embedding model selectable per knowledge index, from the models installed through the wizard (FR-F5a). Changing the model triggers a versioned re-index job. | Catalog: BGE-M3, Qwen3-Embedding, jina-v3, e5, API models | P0 |
| FR-R2 | Reranker selectable per bot, from the installed models, including "none". | Catalog: bge-reranker-v2-m3, Qwen3-Reranker, Cohere/Jina API | P0 |
| FR-R3 | Vector store selectable per install, behind a `VectorStore` interface. | pgvector ✅, Qdrant, Weaviate, Milvus | P0 (pgvector) / P1 (Qdrant) / P2 (others) |
| FR-R4 | Hybrid search: dense + sparse/BM25, fused with reciprocal rank fusion (RRF). | — | P0 |
| FR-R5 | **Permission-filtered retrieval inside the query** (see §7.2). | OpenFGA ✅, SpiceDB | P0 |
| FR-R6 | Query rewriting and conversation-aware follow-up questions. | — | P0 |
| FR-R7 | Citations with document, page, and section; click through to the source with the passage highlighted. When an answer uses a table or figure, the citation shows that table or the figure crop. | — | P0 |
| FR-R8 | Retrieval metrics: recall@k, MRR, nDCG, with separate **Indonesian** and **cross-lingual** (question in Indonesian, source in English, and the reverse) evaluation set. | — | P1 |
| FR-R9 | Advanced RAG: GraphRAG, multimodal (images and charts), routing across knowledge bases. | — | P3 |
| FR-R10 | **Structured-data questions:** answers over spreadsheets and CSV (totals, filters, comparisons) by running a computation on the table instead of reading text chunks. Results show the computed table and the source file. | — | P3 |

### 6.5 Build: prompts, conversation, tools, agents
| ID | Requirement | Tools | Priority |
|---|---|---|---|
| FR-B1 | Prompt registry with versions, labels (production/staging), playground, diffs. | Langfuse ✅, MLflow | P0 |
| FR-B2 | **Conversation memory:** short-term (within a session) and optional long-term user memory, which the user can view and delete. | — | P0 (short) / P2 (long) |
| FR-B3 | Structured-output tests: JSON/schema validity rate per model. | native ✅, Guardrails AI, guided decoding | P1 |
| FR-B4 | Live tools through MCP: one MCP server per system, generated from OpenAPI (see §7.3). | MCP ✅ | P1 |
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
| FR-T13 | **Document-understanding test set:** table QA, chart QA (values read from charts), figure/diagram QA, OCR accuracy (character error rate) on scans, and "safety warning included" checks for manuals. Used to compare baseline parsing vs baseline plus VLM in the Lab, so a company can see whether the vision add-on is worth its GPU cost. | built-in ✅ | P1 |

### 6.7 Release
| ID | Requirement | Priority |
|---|---|---|
| FR-RL1 | **The bot as a versioned bundle:** prompt version + model + index version + reranker + guardrails + tools + config. It is released and rolled back as one unit. | P0 |
| FR-RL2 | Release gates: eval thresholds, zero permission leaks, red-team pass, human sign-off. Configured per bot in P1; set automatically by risk tier once FR-P2 ships (P2). | P1 / P2 |
| FR-RL3 | CI integration: run eval suites from GitHub Actions / GitLab CI and fail the pipeline on regression. | P1 |
| FR-RL4 | Rollout strategies: shadow deploy, canary (traffic %), online A/B test with feature flags. | P2 |
| FR-RL5 | One-click rollback to any previous bundle version. | P1 |
| FR-RL6 | **Environments: dev → staging → prod.** A bot bundle is promoted between environments, never edited in place in prod. Each environment has its own knowledge index, gateway keys, and budgets. Staging uses test or anonymized documents unless an admin explicitly allows production data. Promotion requires that environment's release gates. Single-node installs may run all three as namespaces on one machine. **Optional in the Lite tier**: a single environment, where bundles, versions, release gates, and rollback still apply. | P1 |
| FR-RL7 | **Bot access and knowledge scope:**<br>• Each bot is available only to the users, teams, roles, or divisions it is granted to.<br>• Each bot has a knowledge scope (selected folders or spaces).<br>• **Effective retrieval = bot scope ∩ the asking user's permissions.** A bot never widens what a user can see. | P0 |

### 6.8 Operate
| ID | Requirement | Tools | Priority |
|---|---|---|---|
| FR-O1 | Traces for every chat: retrieval results, prompt, model, tokens, cost, latency, tool calls. | Langfuse ✅, Phoenix, MLflow 3 | P0 |
| FR-O2 | User feedback: thumbs up/down with an optional correction, attached to the trace. | — | P0 |
| FR-O3 | Online evaluation on sampled production traffic. | Langfuse evaluators | P2 |
| FR-O4 | Drift detection: shifts in query topics, embedding drift, quality decay. | — | P2 |
| FR-O5 | SLOs and alerting: latency, error rate, cost per conversation, guardrail trigger rate. | OpenTelemetry → Prometheus/Grafana ✅ | P1 |
| FR-O6 | FinOps: spend per user, team, division, and bot; budgets, alerts, chargeback reports. | LiteLLM spend | P1 |
| FR-O7 | **Usage and ROI analytics:** active users, questions per division, answer rate, deflection, top unanswered topics, estimated time saved. Shown aggregated by team or division; individual-level views only for the person themself, or for admins with an audited reason. | — | P1 |
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
| FR-S10 | Document search (title, content, owner, label, date), filtered by permission exactly like chat retrieval. | P1 |

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
| FR-C9 | Streaming answers with a stop button, citations, copy/export, and feedback. "Why this answer?" (FR-O11) is added in P1. | P0 |
| FR-C10 | Notification when something is shared with you: "X shared Y with you — ask the AI about it." | P0 |
| FR-C11 | Conversation history: list, search, rename, and delete your own conversations; retention follows NFR-10. | P0 |
| FR-C12 | **Grounding and no-existence leaks:**<br>• By default, answers come only from permitted sources and live tools. When nothing relevant is found, the AI says so instead of guessing. Each bot can allow general-knowledge answers, which are then labeled as such.<br>• Answers and errors never reveal that a restricted document exists: no titles, no "you don't have access to X". Hinting at existence counts as a leak in FR-T7. | P0 |
| FR-C13 | **Answer language:** the AI answers in the language of the question, even when sources are in another language, and keeps quotes and citations in the original language. | P0 |
| FR-C14 | **Built-in chat UI** in the Next.js app, built with the open-source **assistant-ui** components (MIT): streaming, stop, markdown, attachments, conversation list, and custom citation and figure-crop components. It talks only to our API, so every permission rule applies. | P0 |
| FR-C15 | **Alternative chat front-ends (optional):** an OpenAI-compatible endpoint exposes each bot as a "model", so LibreChat (MIT) or another OpenAI-compatible client can be used. The client must authenticate **as the end user** (shared OIDC SSO or the user's own API key, never a shared service key). Its own document upload and RAG features are disabled, so all knowledge goes through our permission-filtered pipeline. Open WebUI is not supported on the live path: its license requires keeping its branding above 50 users, and its own RAG and user model would bypass our permissions. | P2 |

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

Targets are for the Standard and Enterprise reference hardware (§12) and must be validated in Phase 1–2 load tests. In the **Lite tier**, performance and availability targets (NFR-1 to NFR-5) are best effort: measured and displayed, but not release gates. Security, permission, privacy, and audit requirements (NFR-7 to NFR-11, NFR-18 to NFR-20) apply in full in every tier.

| ID | Category | Requirement |
|---|---|---|
| NFR-1 | Performance | Chat time to first token, p95: **≤ 3 s** (GPU profile, 8B model) / **≤ 8 s** (CPU profile, ≤ 4B quantized model). |
| NFR-2 | Performance | Permission-filtered hybrid retrieval with rerank, p95: **≤ 800 ms** at 1M chunks. |
| NFR-3 | Performance | Ingestion: **≥ 20 pages/min** on CPU and **≥ 100 pages/min** on GPU (Docling). |
| NFR-4 | Scalability | GPU reference profile supports **≥ 200 concurrent chat users**. Scales horizontally on Kubernetes. pgvector up to ~20M chunks; Qdrant beyond that. |
| NFR-5 | Availability | Single node: best effort, with backups. HA profile (Kubernetes): **99.9%** monthly for the chat API. |
| NFR-6 | Durability | Daily backups of Postgres, vector store, object storage, OpenFGA, and Langfuse (ClickHouse traces). Restore tested quarterly. RPO ≤ 24 h, RTO ≤ 4 h (single node); RPO ≤ 1 h (HA). Backups use documented, open formats and restore onto a fresh install, so the company can always export and leave. |
| NFR-7 | Security | TLS everywhere; encryption at rest; secrets in Vault or Kubernetes secrets; no plaintext credentials in the database or logs. |
| NFR-8 | Security | Permission correctness: **0 leaks** in the leak suite is a release gate. Access changes apply in ≤ 5 s. |
| NFR-9 | Security | Supply chain: pinned image digests, hash-locked dependencies, SBOM per release, dependency and container scanning in CI, signed release artifacts. |
| NFR-10 | Privacy and compliance | Configurable retention, with defaults: chats 1 year, traces 90 days (30 days until FR-O12 masking ships), audit log 1 year, trash 30 days. Data-subject requests (export or delete a person's data). Legal hold. Data stays on premises by default. Supports UU PDP No. 27/2022 obligations; GDPR-ready. |
| NFR-11 | Auditability | Every access-relevant action is audited, immutable, kept ≥ 1 year (configurable), and exportable to a SIEM. |
| NFR-12 | Portability | Runs on Linux x86_64 with Docker Compose or Kubernetes 1.29+. Works fully air-gapped. NVIDIA GPU optional. **No outbound telemetry or update checks by default.** |
| NFR-13 | Usability | Indonesian + English UI. Responsive layout that works in mobile browsers. A new business user can ask a first question within 2 minutes of logging in, with no training. |
| NFR-14 | Accessibility | WCAG 2.1 AA for the chat, documents, and sharing screens. |
| NFR-15 | Maintainability | Every Lab adapter has contract tests and a nightly smoke test. Tool versions are pinned and upgraded deliberately. |
| NFR-16 | Observability | All services emit OpenTelemetry traces, metrics, and logs, and expose health and readiness endpoints. Each LLM call has a trace ID shown to admins and linked from feedback. |
| NFR-17 | Licensing | Platform code is under a permissive open-source license (proposed: Apache 2.0). AGPL tools run as separate services only. The license of every tool and model is shown before install. |
| NFR-18 | Application security | The web app and API meet OWASP ASVS Level 2: session timeout (default 8 h idle), CSRF protection, content security policy, login rate limiting, MFA through the identity provider. An external penetration test is run before GA, and its critical/high findings are fixed. |
| NFR-19 | Resilience | **Permission checks fail closed:** if OpenFGA or the identity provider is unreachable, access is denied, never granted. Every external call (models, tools, stores) has a timeout and retry policy. If the chat model fails, the gateway falls back to a configured backup model or the UI shows a clear error. A failing optional component (Langfuse, VLM, guardrails, Lab tools) degrades its feature without taking chat down, except guardrails marked mandatory for a bot, which block that bot instead. |
| NFR-20 | API and data standards | REST API versioned under `/api/v1`, with OpenAPI generated from code, cursor pagination, idempotency keys for create operations, and one error format (RFC 9457 problem details) with messages in EN/ID. IDs are UUIDv7. Timestamps are stored in UTC and displayed in the user's time zone (default Asia/Jakarta). Every record has created/updated by and at. User-facing errors never expose stack traces or internal names. |

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
| Chat UI | Built-in, with assistant-ui (FR-C14) | LibreChat through the OpenAI-compatible endpoint (FR-C15) |
| System of record | PostgreSQL | — |
| Queue / cache | Redis | — |
| Job / workflow engine | Celery (on Redis) | Temporal (FR-F20) |
| Identity / SSO | OIDC (Keycloak bundled optional), SCIM | Azure AD, Google Workspace |
| Document authorization | OpenFGA | SpiceDB |
| Model gateway | LiteLLM (pinned, digest-verified) | Portkey, Kong AI |
| Serving | Ollama (CPU), vLLM (GPU) | SGLang, TensorRT-LLM |
| Object storage | SeaweedFS | Garage, RustFS, Ceph, external S3 |
| Parsing | Docling (every tier, FR-D3) | Unstructured, MinerU (Lab comparison only) |
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

## 12. Install tiers and reference hardware

The wizard recommends a tier from the detected hardware (FR-F19). The user can override the recommendation.

| Tier | For | Reference hardware | Use |
|---|---|---|---|
| **Lite** | A solo developer or learner on a laptop or PC, with no server | 4+ cores, 16 GB RAM, 50 GB free disk. GPU optional (≥ 6 GB VRAM speeds up local models). | Learning, prototyping, demos, ≤ 5 users |
| **Lite + API** | Same, but with no capacity for local models | Same as Lite; no GPU needed | Models run on external APIs (OpenAI, Anthropic, Gemini, …) through the gateway. Requires the egress setting (FR-M9) to be enabled. |
| **Standard (CPU)** | Team pilot on one server | 16 vCPU, 64 GB RAM, 500 GB SSD, no GPU | Pilot, ≤ 30 concurrent users, quantized models ≤ 4B |
| **Standard (GPU)** | Department production | 32 vCPU, 128 GB RAM, 1 TB NVMe, 1× 48–80 GB GPU (e.g., L40S / A100 / H100) | ≤ 200 concurrent users, 8B–32B models |
| **Enterprise HA** | Company-wide | Kubernetes, 3+ nodes, GPU node pool | 99.9% availability |

**What changes in the Lite tier:**

| Concern | Standard / Enterprise | Lite |
|---|---|---|
| Model serving | Ollama (CPU) or vLLM (GPU); SGLang later | **Ollama only**, or a llama.cpp server, or external APIs. Small quantized models (≤ 4B on CPU or 6 GB GPUs). |
| Environments | dev → staging → prod (FR-RL6) | **Single environment** |
| Login | Keycloak (OIDC SSO) | **Built-in local accounts** plus the bootstrap admin; OIDC can be connected later |
| Tracing | Langfuse (needs ClickHouse) | **Built-in trace table in Postgres** with a basic viewer; Langfuse is an opt-in Lab tool |
| Infra metrics | Prometheus + Grafana | Off; a built-in health page instead |
| Guardrails | NeMo Guardrails + Llama Guard | Llama Guard through Ollama, optional |
| Vision add-on (FR-D15) | GPU-served VLM (e.g., through vLLM) | A small VLM through Ollama (fits 6 GB VRAM, slower), or an external vision API for non-confidential documents; baseline parsing works without it |
| Lab tools | Any `lab-*` profile | Opt-in, one stage at a time, to fit memory |
| Job engine | Celery or Temporal (FR-F20) | **Celery only** (Temporal adds a server the laptop does not need) |
| Backups | Scheduled backups of every store | `make backup` (database dump + files), run manually or by cron |
| Deployment | Compose or Helm | Docker Compose only |

**Never removed in any tier:** Postgres with pgvector, Redis, OpenFGA permissions, the LiteLLM gateway, SeaweedFS, the permission-leak suite, the audit log, pinned versions, and secret handling. Every tier has the same chat, sharing, and permission behavior.

**Lite resource target:** the platform stack, excluding model memory, uses ≤ 6 GB RAM. This target must be validated in Phase 0.

---

## 13. Release plan

| Phase | Duration | Scope | Exit criteria |
|---|---|---|---|
| **0: Foundations** | ~2 wks | Monorepo, CI, pinned dependencies; **Lite tier first** (Postgres, Redis, LiteLLM, SeaweedFS, Ollama, OpenFGA; local accounts plus bootstrap admin), then the Standard additions (Keycloak/OIDC, Langfuse); org model; reversible DB migrations; adapter framework; audit log; **CLI install wizard with hardware detection and model selection** | The wizard detects hardware, recommends a tier, and the user picks models; Lite comes up healthy on a 16 GB laptop within the ≤ 6 GB stack target; login works; the chosen model answers through the gateway |
| **1: MVP** | ~8 wks | All P0: upload/parse/chunk/embed, sharing, permission-aware chat with citations and scopes, bot bundles, Ragas evals, leak suite, feedback, traces, EN/ID UI | US1–US4, US13, and US14 pass on **both Lite and Standard (CPU)**; **0 leaks** (including no-existence leaks, FR-C12); NFR-1/2 met for CPU; an eval report is produced |
| **2: Lab** | ~6 wks | All P1: Eval Lab (DeepEval, Phoenix, promptfoo, hybrid judging, evaluate-the-evaluators), Retrieval Lab, vLLM, benchmark runner, live tools v1 (read-only), release gates and CI, guardrails, model routing, FinOps, ROI analytics, public API/SDK | US5–US8 and US15 pass; comparison reports for evaluation, retrieval, and serving; GPU NFRs met |
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
| Confidential data sent to an external model API | Critical | External APIs off by default; egress policy per sensitivity label enforced at the gateway (FR-M9); blocked calls audited. |
| VLM misreads a figure (e.g., a wrong torque value from a diagram), causing an unsafe repair | Critical | Numbers quoted from text/tables first; figure-only values flagged and shown with the image crop; safety warnings quoted verbatim (FR-D16); document-understanding tests (FR-T13); human review option for high-risk manual folders. |
| Malicious uploads (malware, hidden prompt injection) | High | Malware scan and quarantine (FR-D14); retrieved text treated as untrusted (FR-C8); red-team suite (FR-T8). |
| Langfuse (ClickHouse) too heavy for small machines | Low | Lite tier uses built-in Postgres tracing; Langfuse is opt-in there. |
| Celery and Temporal behave differently (retries, ordering, cancellation) | Medium | One job interface; idempotent steps; job contract tests run against both engines in CI. |
| Lite and Standard drift apart (bugs that appear in only one tier) | Medium | One codebase; tiers differ only by configuration behind interfaces; `make verify-phase-N` runs on both Lite and Standard. |
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
| ~~Q6~~ | ~~OCR for scanned documents in the MVP?~~ **Resolved:** baseline OCR, tables, and figure crops (Docling) in P0 for every tier; an optional vision-model add-on for complex documents in P1 (FR-D3, FR-D15, FR-D16). | Product | Phase 1 |
| Q7 | Will there be a hosted demo / training environment? | Owner | Phase 3 |

---

**Defaults if a question is still open when its phase starts.** Builders use these and log them in the Decisions section of `AGENTS.md`:
- **Q2:** Keycloak, bundled, as the OIDC provider. Other providers connect to Keycloak or directly through OIDC later.
- **Q3:** Apache 2.0.
- **Q5:** No external sharing in the MVP. The sharing model must not rule it out later (keep a "guest" principal type in the OpenFGA model).

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
| **OIDC** | OpenID Connect: the standard login protocol used for SSO. |
| **RRF** | Reciprocal Rank Fusion: merges the rankings of dense (vector) and keyword search into one list. |
| **recall@k / MRR / nDCG** | Retrieval metrics: whether the right passage is in the top k, how high the first correct one ranks, and overall ranking quality. |
| **SLO** | Service Level Objective: a measurable target (e.g., p95 latency ≤ 3 s). |
| **RPO / RTO** | Recovery Point / Time Objective: maximum data loss and maximum downtime after a failure. |
| **OWASP ASVS** | Application Security Verification Standard: a checklist of web-app security requirements, by level. |
| **Data egress** | Data leaving the company's environment, e.g., text sent to an external model API. |
| **OCR** | Optical character recognition: turning scanned images of text into text. |
| **VLM** | Vision-language model: an AI model that reads images (figures, charts, scanned pages) together with text. |

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
workers/              ingestion, eval, and benchmark jobs behind one job interface (Celery by default; Temporal optional, FR-F20)
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
- A phase is done only when `make verify-phase-N` passes on both the Lite tier and Standard (CPU) (§12). "It works on my machine" doesn't count.

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
| Chat | Scope selector, streaming answers, citations, feedback, model/bot picker, conversation history (FR-C11) |
| Documents | My documents / Shared with me / My team; folders; upload; trash with restore (FR-D9) |
| Share dialog | Add a user, team, role, division, or company; set the permission level; see who has access |
| Document viewer | Open a cited passage with highlighting |
| Admin → Org | Divisions, teams, users, roles; deactivate a user and transfer ownership (FR-F18) |
| Admin → Models | Installed models per role, gateway providers, external-API switch (FR-M9), test prompt |
| Eval | Datasets, run an eval, run results, run-vs-run comparison, leak-suite results |
| Bots | Bot bundles, versions, release and rollback; who can use the bot and its knowledge scope (FR-RL7) |

### 17.9 Developer setup
- `make dev` starts the Lite tier with hot reload for the API, web, and workers, and seeds the demo org (Andi, Budi, an intern) plus sample documents.
- `make test` runs everything that doesn't need a model; `make test-all` also runs model-backed tests against a small local model.
- New contributors are productive in ≤ 30 minutes from `git clone`, following `AGENTS.md`.

### 17.10 Test strategy
| Level | What | Tooling | When |
|---|---|---|---|
| Unit | Pure logic: chunking, permission resolution, config validation, routing rules | pytest, Vitest | Every commit |
| Integration | Real Postgres, Redis, OpenFGA, SeaweedFS in containers | pytest + Testcontainers | Every commit |
| Contract | Every adapter, the vector-store/storage/job/tracing interfaces against each implementation (e.g., Celery and Temporal) | pytest | Every commit touching an interface |
| Permission-leak suite | Personas probing forbidden content, including no-existence leaks | built-in (FR-T7) | Every commit touching documents, retrieval, chat, cache, or sharing; release gate |
| E2E user stories | `test_usNN_*` through the real UI and API | Playwright + pytest | `make verify-phase-N`, nightly |
| Quality evals | Ragas and others on gold sets | Eval Lab | Bot release gate |
| Security | Dependency, container, and secret scanning; SAST; ASVS checks | e.g., Trivy, gitleaks, Semgrep (verify per §17.6) | Every PR; pen test before GA |
| Load | Chat and retrieval latency/throughput | k6, guidellm | Before each phase exit (Standard and above) |

Coverage target: ≥ 80% lines for API and workers. 100% of permission-resolution and sharing code paths are covered by tests.

### 17.11 CI/CD and versioning
- **Every PR:** lint, format check, type check (mypy/pyright, tsc), unit + integration + contract tests, leak suite when relevant, security scans, build images.
- **Every release:** SBOM, signed images, pinned digests written to `deploy/versions.lock`, upgrade test from the previous release (FR-F16), release notes.
- **Versioning:** the platform uses semantic versioning. Commits follow Conventional Commits and reference requirement IDs. `main` is always releasable; work happens on short-lived branches.
- **Code standards:** Python with ruff and type hints throughout; TypeScript in strict mode; no secrets in code; structured JSON logs with trace IDs.

---

# Part II — Technical Design

Part I says *what* to build; Part II says *how*. Builders follow Part II unless an entry in the Decisions section of `AGENTS.md` overrides it (§17.5). Library and version choices are re-verified at the start of each phase (§17.6).

## T1. Architecture: a modular monolith plus infrastructure services

**Decision:** one API application (FastAPI) and one worker application share the same Python package and are split into modules. They are not microservices. The only separate processes are infrastructure (databases, gateway, model servers) and Lab tools (one container each, FR-F8).
**Why:** fewer moving parts to build, deploy, and debug; module boundaries can still be split into services later if needed.

| Process | Lite | Standard | Notes |
|---|---|---|---|
| `web` (Next.js) | ✅ | ✅ | UI only; talks to `api`. Chat UI built with assistant-ui (T9, FR-C14) |
| `api` (FastAPI) | ✅ | ✅ | All HTTP endpoints, SSE chat streaming |
| `worker` | ✅ Celery | ✅ Celery or Temporal worker | Same job code (T2) |
| `postgres` (+pgvector ≥ 0.8) | ✅ | ✅ | System of record, vectors, built-in traces (Lite) |
| `redis` | ✅ | ✅ | Celery broker, cache, sessions, rate limits |
| `openfga` | ✅ | ✅ | Uses the same Postgres instance (its own database) |
| `litellm` | ✅ | ✅ | Model gateway; its own database in the same Postgres |
| `seaweedfs` | ✅ | ✅ | S3 API for files and figure crops |
| `ollama` | ✅ | ✅ (CPU) | Chat LLM and small VLM |
| `tei` | ✅ | ✅ | Embedding and reranker serving (Hugging Face Text Embeddings Inference; CPU or GPU image) |
| `caddy` | ✅ | ✅ | Reverse proxy and TLS (local CA on Lite); the only exposed port |
| `keycloak` | — | ✅ | OIDC SSO |
| `langfuse` (+clickhouse) | opt-in | ✅ | Tracing |
| `temporal` | — | opt-in | Only if chosen in FR-F20 |
| `vllm` | — | GPU only | GPU chat/VLM serving |
| `clamav` | P1 | P1 | Malware scanning |
| `prometheus`, `grafana` | — | ✅ | Infra metrics |
| `librechat` | — | opt-in (P2) | Alternative chat front-end (FR-C15) |
| Lab tool containers | opt-in | opt-in | `adapters/<stage>/<tool>` |

**Lite memory budget (excluding model memory):**

| Process | Budget |
|---|---|
| postgres | 768 MB |
| worker (Docling models loaded) | 2 GB |
| api | 512 MB |
| litellm | 512 MB |
| seaweedfs | 256 MB |
| web | 256 MB |
| openfga | 128 MB |
| redis | 64 MB |
| caddy | 32 MB |
| **Total** | **≈ 4.5 GB** (target ≤ 6 GB, §12) |

Ollama and TEI memory count as model memory.

## T2. Code structure and swap points

```
apps/api/src/e2eai/
  core/        config (FR-F21), db session, errors (RFC 9457), i18n, logging, ids (UUIDv7)
  ports/       the ONLY interfaces in the codebase (see table below)
  adapters/    implementations of ports (pgvector.py, qdrant.py, celery_engine.py, temporal_engine.py, ...)
  modules/
    auth/      local accounts, OIDC, sessions, API keys
    org/       organizations, divisions, teams, users, roles, offboarding
    authz/     OpenFGA client, principal resolution, doc_principals index (T4)
    documents/ folders, documents, versions, trash, legal hold
    sharing/   shares, access requests, notifications on share
    ingest/    parse (Docling), chunk, embed, VLM enrichment (job definitions)
    retrieval/ hybrid search, rerank, citations
    chat/      conversations, messages, answer pipeline (T5), OpenAI-compatible bot endpoint (FR-C15)
    bots/      bundles, versions, release/rollback, access, scope
    evals/     datasets, runs, judges (via Lab adapters), leak suite
    admin/     models, settings, egress policy, config export
    audit/     append-only hash-chained log
  jobs/        job functions, engine-agnostic (called by Celery or Temporal)
  main.py      FastAPI app;   worker.py   worker entrypoint
```

Each module contains `router.py` (HTTP), `service.py` (logic), `repo.py` (SQL), and `schemas.py` (Pydantic). Modules call each other only through `service.py`.

**Ports.** Interfaces exist *only* where a tier, a Lab comparison, or a phase actually swaps the implementation (ponytail rule: no interface with one implementation):

| Port | Implementations | Swapped by |
|---|---|---|
| `VectorStore` | pgvector (P0), Qdrant (P1) | Lab, scale |
| `JobEngine` | Celery (P0), Temporal (P1) | FR-F20 |
| `TraceSink` | Postgres (P0), Langfuse (P0, Standard) | Tier |
| `AuthProvider` | Local (P0), OIDC (P0, Standard) | Tier |
| `Parser` | Docling (P0); other parsers through Lab adapters | Lab |

**Not ports:**
- **Models:** every model call (chat, embeddings, VLM) goes through LiteLLM as one OpenAI-compatible client. Reranking calls TEI's `/rerank` directly unless LiteLLM's rerank routing is verified to work with TEI (§17.6).
- **File storage:** one S3 client; SeaweedFS and external S3 differ only in endpoint config.
- **Authorization:** OpenFGA through the `authz` module. SpiceDB is a Lab comparison only, run through an adapter, never on the live path.

## T3. Data model (PostgreSQL)

Conventions (NFR-20): UUIDv7 `id`; `created_at`/`updated_at` (UTC); `created_by`/`updated_by`; migrations with Alembic, each one reversible (FR-F16).

| Area | Tables (key columns) |
|---|---|
| Org | `organizations`; `divisions(org_id)`; `teams(division_id)`; `users(email, display_name, status[active/disabled], division_id, manager_id, locale, time_zone)`; `team_members(team_id, user_id)`; `roles(name)`; `user_roles(user_id, role_id, project_id NULL)`; `projects(owner_team_id/owner_division_id)` |
| Auth | `local_credentials(user_id, password_hash[argon2id])`; `api_keys(user_id, hash, scopes, expires_at, revoked_at)`; sessions live in Redis |
| Documents | `folders(parent_id, owner_id, path)`; `documents(folder_id, owner_id, title, sensitivity, status[active/trashed/purged], trashed_at, legal_hold, current_version_id)`; `document_versions(document_id, object_key, sha256, mime, size, parse_status, parse_confidence, scan_status)` |
| Chunks | `chunks(document_id, version_id, ordinal, kind[text/table/figure/vlm], text, page, section_path, figure_object_key, table_json, tsv tsvector)` |
| Indexes | `knowledge_indexes(embedding_model, dim, chunker, version, status)`; **one table per index:** `emb_<index_id>(chunk_id PK, embedding vector(dim))` with an HNSW index. The dimension is fixed per table, so changing models means a new index (FR-R1). |
| Permissions read-index | `doc_principals(document_id, principal, level, expires_at NULL)`, PK on (document_id, principal), index on (principal, document_id); see T4 |
| Bots | `bots`; `bot_versions(prompt_ref, chat_model, index_id, reranker, guardrails_json, tools_json, released_at)`; `bot_scope(bot_id, folder_id)` |
| Chat | `conversations(user_id, bot_id, title)`; `messages(conversation_id, role, content, model, tokens, latency_ms)`; `citations(message_id, document_id, version_id, chunk_id, page)` |
| Evals | `datasets`; `dataset_items(input, expected, persona)`; `eval_runs(bot_version_id, dataset_version, frameworks, config_json, seeds)`; `eval_results(run_id, item_id, framework, metric, score, judge_prompt_ref)`; `human_reviews` |
| Ops | `audit_log(seq, at, actor, action, target, details_json, prev_hash, hash)`; `outbox(topic, payload, processed_at)`; `traces` (Lite TraceSink); `notifications`; `settings` |

## T4. Permission design (the critical part)

**Source of truth:** OpenFGA holds every sharing relationship and answers point checks: can this user open, share, or delete this document, or use this bot.

**Search filtering:** for chat and search, OpenFGA's own guidance for large result sets is a *local index*, because ListObjects is capped at 1,000 results. That index is `doc_principals`.

**OpenFGA model (DSL):**
```
model
  schema 1.1
type user
type org
  relations
    define member: [user]
type division
  relations
    define member: [user]
type team
  relations
    define member: [user]
type role
  relations
    define member: [user]
type guest            # reserved for external sharing (Q5); unused in the MVP
type folder
  relations
    define parent: [folder]
    define owner: [user]
    define editor: [user, team#member, division#member, role#member, org#member, user with non_expired, team#member with non_expired] or owner or editor from parent
    define viewer: [user, team#member, division#member, role#member, org#member, user with non_expired, team#member with non_expired] or editor or viewer from parent
type document
  relations
    define parent: [folder]
    define owner: [user]
    define editor: [user, team#member, division#member, role#member, org#member, user with non_expired, team#member with non_expired] or owner or editor from parent
    define viewer: [user, team#member, division#member, role#member, org#member, user with non_expired, team#member with non_expired] or editor or viewer from parent
type bot
  relations
    define admin: [user]
    define user: [user, team#member, division#member, role#member, org#member] or admin
condition non_expired(current_time: timestamp, expires_at: timestamp) {
  current_time < expires_at
}
```
(Expiring shares, FR-S4, use the `non_expired` condition. The same condition can be added to division, role, and org grants if needed.)

**Read-index rules:**
1. `doc_principals` stores the *granted principal* (`user:…`, `team:…`, `division:…`, `role:…`, `org:…`), **not** expanded to individual users. Org changes (Andi moves division) therefore need no index update; they change only principal resolution.
2. Folder grants are expanded onto every document under that folder when written, moved, or added.
3. **Tighten first, loosen last.** On revoke, delete the `doc_principals` row *before* deleting the OpenFGA tuple. On grant, write OpenFGA *before* inserting the row. A partial failure can therefore only ever be *more restrictive* than the truth, never more permissive (fail closed, NFR-19).
4. A reconciler job reads OpenFGA's ReadChanges stream every few seconds and repairs any drift in `doc_principals`. Every repair is logged.
5. Expired shares are filtered at query time (`expires_at > now()`). A cleanup job removes them later.

**User principal set:** computed per request from the org tables and cached in Redis for ≤ 5 s. It is `{user:<id>, org:<id>, division:<id>, team:<ids>, role:<ids>}`. Deactivated users get an empty set (FR-F18).

**Filtered retrieval query (pgvector):**
```sql
SET LOCAL hnsw.iterative_scan = relaxed_order;      -- pgvector ≥ 0.8: keeps recall under filters
SELECT c.id, c.document_id, c.page, c.text, e.embedding <=> :qvec AS dist
FROM emb_<index> e
JOIN chunks c     ON c.id = e.chunk_id
JOIN documents d  ON d.id = c.document_id AND d.status = 'active' AND c.version_id = d.current_version_id
WHERE c.document_id IN (SELECT document_id FROM doc_principals
                        WHERE principal = ANY(:principals)
                          AND (expires_at IS NULL OR expires_at > now()))
  AND c.document_id IN (SELECT document_id FROM bot_scope_documents WHERE bot_id = :bot)   -- FR-RL7
ORDER BY dist LIMIT :k;
```
The keyword half runs the same filters against `tsv` (or `pg_search` BM25, if verified). The two lists are merged with reciprocal rank fusion (RRF) in Python.

**Qdrant (P1):** each point's payload holds `document_id` and `principals[]`. A share change updates the payload by `document_id` filter. The same tighten-first rule applies.

**Cache keys** include `sha256(sorted principals + bot_version + index_version)` (FR-C5).

## T5. Key flows

**F1 — Upload and ingest (FR-D1, D3, D9, D14)**
1. `POST /api/v1/documents` (multipart) → check auth, limits (FR-F15), and the caller's folder editor permission (OpenFGA Check).
2. Store the file in S3 under key `sha256/<hash>`; insert `documents` and `document_versions` rows. In the same transaction: owner `doc_principals` row, audit row, and an outbox event.
3. Write the OpenFGA owner tuple (an outbox retry covers failures). Enqueue `ingest(version_id)`.
4. Worker: malware scan (P1) → Docling parse → chunks (text, tables as `table_json` plus text, figures as crops in S3) → embed in batches through TEI → upsert into `emb_<index>` → `parse_status = ready` → notify the owner.
5. Pages flagged low-confidence or figure-heavy → enqueue `vlm_enrich(version_id, pages)` (P1, FR-D15).
6. Every job step is idempotent and keyed by `version_id`; retries are safe.

**F2 — Share and revoke (FR-S1–S3, C4)**
1. `POST /api/v1/documents/{id}/shares` → Check `owner` → policy check (sensitivity label, P1).
2. Write the OpenFGA tuple → insert `doc_principals` (loosen last) → audit → notify recipients.
3. `DELETE …/shares/{share_id}` → delete `doc_principals` (tighten first) → delete the OpenFGA tuple → invalidate affected cache keys → audit.

**F3 — Chat answer (FR-C1–C13)**
1. `POST /api/v1/chat/conversations/{id}/messages` → Check bot `user` → resolve principals.
2. Rewrite the query using conversation context.
3. Filtered hybrid retrieval (T4) → rerank → assemble context with citation markers.
4. Egress check: the highest sensitivity label in the context vs. the chat model's destination (FR-M9). If blocked, use the local fallback model or return a clear error.
5. Input guardrails (P1) → stream generation through LiteLLM over SSE → output guardrails (P1).
6. Save the message, citations (with `version_id`), and trace (TraceSink).
7. If nothing relevant is permitted: a grounded "I couldn't find this in the documents you can access" answer with no hints about other documents (FR-C12).

**F4 — Delete, trash, purge (FR-D9, D13)**
- Trash sets `status = 'trashed'`. Retrieval filters on `status = 'active'`, so the document disappears **immediately** (well within the 5-minute requirement). Cache entries are invalidated.
- A daily purge job deletes files, chunks, and embeddings after 30 days, skipping documents under legal hold.

**F5 — Offboarding (FR-F18)**
1. Set `status = disabled` → delete the user's Redis sessions and revoke their API keys (≤ 1 min).
2. Transfer ownership: OpenFGA owner tuples plus `documents.owner_id` → remove org memberships → audit.

**F6 — Eval and leak-suite run (FR-T1–T7)**
1. Job runs each dataset item through the F3 pipeline **as the item's persona**, using that persona's principals; never a bypass.
2. Judges run in Lab adapter containers through HTTP (T6). Results are stored per framework and metric.
3. Leak suite: personas ask about forbidden documents. Any forbidden `document_id` in the retrieved set, any forbidden title or content in the answer, or any existence hint fails the run.

**F7 — Alternative chat front-end (FR-C15, P2)**
1. LibreChat (or another OpenAI-compatible client) sends `POST /api/v1/openai/chat/completions` with `model = <bot id>`.
2. It authenticates **as the end user**: OIDC SSO shared through Keycloak, or the user's own API key. It never uses a shared service key.
3. The request runs the same F3 pipeline with that user's principals, so permissions behave exactly as in the built-in UI.
4. The front-end's own document upload and RAG features are disabled. All knowledge goes through the permission-filtered pipeline.

## T6. Lab adapter contract

Every Lab tool container exposes the same HTTP API, so the platform never imports tool libraries (each tool's dependencies stay in its own container):

| Endpoint | Purpose |
|---|---|
| `GET /info` | Tool name, version, license, stage, supported metrics/operations |
| `GET /health` | Liveness |
| `POST /run` | Body: `{run_id, operation, inputs[], config, judge: {base_url, model}}`. Returns normalized `{item_id, metric, score, details, judge_prompt}` rows |

Judge and model calls from inside adapters go through LiteLLM, using a per-run virtual key so cost is tracked (FR-L4). Contract tests live in `adapters/_contract/` and every adapter must pass them.

## T7. API surface (v1)

All routes are under `/api/v1`; errors use RFC 9457.

| Group | Main endpoints |
|---|---|
| Auth | `POST /auth/login` (local), `GET /auth/oidc/callback`, `POST /auth/logout`, `GET /me` |
| Org | `/divisions`, `/teams`, `/users` (`POST /users/{id}/deactivate`), `/roles`, `/memberships` |
| Documents | `/folders`; `/documents` (`?view=mine\|shared\|team\|trash`), `POST /documents` (upload), `/documents/{id}`, `/versions`, `/download`, `POST /restore`, `DELETE ?permanent=true` |
| Sharing | `/documents/{id}/shares`, `/folders/{id}/shares`, `/access-requests` (P1) |
| Chat | `/chat/conversations` (CRUD), `POST /chat/conversations/{id}/messages` (SSE stream), `POST /messages/{id}/feedback`, `POST /messages/{id}/stop` |
| OpenAI-compatible (P2) | `GET /openai/models` (bots the user may use), `POST /openai/chat/completions` (FR-C15) |
| Bots | `/bots`, `/bots/{id}/versions`, `POST …/release`, `POST …/rollback`, `/bots/{id}/access`, `/bots/{id}/scope` |
| Search | `GET /search` (P1) |
| Evals | `/evals/datasets`, `/evals/runs`, `GET /evals/runs/{id}/compare?with=`, `/leak-suite/runs` |
| Admin | `/admin/models`, `/admin/settings` (egress, limits), `GET /admin/config/export` (P1) |
| Ops | `/audit` (query, export), `/notifications`, `/health`, `/ready` |

- **Web sessions:** httpOnly, Secure, SameSite=Lax cookie plus a CSRF token.
- **API clients (P1):** `Authorization: Bearer <api key>`.

## T8. Configuration file (FR-F21)

`e2eai.yaml` is validated with Pydantic at startup. Secrets are only referenced (`env:` or `file:`).
```yaml
tier: lite                      # lite | standard | enterprise
components:
  auth: local                   # local | oidc
  job_engine: celery            # celery | temporal
  vector_store: pgvector        # pgvector | qdrant
  tracing: postgres             # postgres | langfuse
  chat_frontends: [builtin]     # builtin | librechat (P2)
models:                         # chosen in the wizard (FR-F5a); no defaults shipped
  chat:      [{name: example-chat-4b-q4, served_by: ollama}]
  embedding: [{name: example-embedding, served_by: tei}]
  reranker:  [{name: example-reranker, served_by: tei}]
  vision:    []                 # FR-D15, optional
egress:
  external_apis: false          # FR-M9
limits: {upload_mb: 100, files_per_batch: 50, storage_gb_per_user: 20}
retention: {chats_days: 365, traces_days: 30, trash_days: 30, audit_days: 365}
locale: {default_language: id, time_zone: Asia/Jakarta}
secrets:
  db_password: env:E2EAI_DB_PASSWORD
```
Model names above are placeholders showing the format; the wizard fills in real choices.

## T9. Cross-cutting implementation choices

All of these are re-verified per §17.6 before first use.

| Concern | Choice |
|---|---|
| Python tooling | uv, ruff, pyright/mypy; Python 3.12 |
| API | FastAPI, Pydantic v2, pydantic-settings |
| Database | SQLAlchemy 2 (async) + asyncpg; Alembic migrations; pgvector ≥ 0.8 |
| Jobs | Celery 5 (Redis broker); `temporalio` SDK for the Temporal engine |
| Authorization | OpenFGA server + official Python SDK; model kept in `deploy/openfga/model.fga` with tests (`fga model test`) |
| Models | `openai` Python SDK pointed at LiteLLM; TEI for embeddings and rerank |
| Parsing | Docling (in the worker image); figure crops to S3 |
| S3 | `aioboto3` |
| Password hashing | argon2id |
| Audit log | Append-only table; each row stores `hash = sha256(prev_hash + row)`, so tampering breaks the chain (FR-F9). A nightly job verifies the chain. |
| Outbox | Postgres `outbox` table processed by a worker, for OpenFGA writes, notifications, and webhooks; at-least-once delivery, idempotent consumers |
| Logging and tracing | Structured JSON logs with trace IDs; OpenTelemetry SDK |
| Frontend | Next.js (App Router, TypeScript strict), Tailwind CSS + shadcn/ui, next-intl (EN/ID), TanStack Query |
| Chat UI | **assistant-ui** (MIT, React): message list, streaming, stop button, attachments, markdown, and custom citation components. Connected to our SSE endpoint, so our backend keeps full control of permissions. |
| Testing | pytest, Testcontainers, Vitest, Playwright |
| Reverse proxy | Caddy (automatic TLS; local CA on Lite) |

## T10. Phase 0 implementation slice

Phase 0 builds, in this order:
1. Repo layout (§17.2), `make dev` / `make test`, CI skeleton.
2. Compose Lite profile (T1), `deploy/versions.lock`.
3. `core/` (config, errors, ids, logging) with `e2eai.yaml` validation.
4. Alembic baseline migration: org, auth, audit, settings tables.
5. Local auth plus bootstrap admin (FR-F2a).
6. OpenFGA model plus model tests; the `authz` module with principal resolution.
7. Hash-chained audit log.
8. CLI wizard: hardware detection, tier recommendation, model selection, config generation (FR-F5, F5a, F5b, F19, F20, F21).
9. LiteLLM wiring: the chosen model answers.
10. Port definitions with their first implementations (pgvector, Celery, Postgres TraceSink, local AuthProvider) plus contract-test scaffolding.
11. Standard additions: Keycloak/OIDC, Langfuse.

**Exit:** `make verify-phase-0` passes (§13).

## T11. Design decisions (approved by the owner, 2026-10-05)

| # | Decision | Status |
|---|---|---|
| D1 | Search filtering uses a Postgres read-index (`doc_principals`) synced from OpenFGA, with the tighten-first rule and a reconciler (T4) | ✅ **Approved.** It follows OpenFGA's documented guidance for search, and ListObjects alone caps at 1,000 objects. |
| D2 | Modular monolith instead of microservices (T1) | ✅ **Approved.** Fewer moving parts. |
| D3 | TEI serves embeddings and rerankers in every tier, instead of Ollama for embeddings | ✅ **Approved.** One server handles both, and Ollama doesn't serve rerankers. |
| D4 | One vector table per knowledge index (fixed dimension) | ✅ **Approved.** pgvector indexes need a fixed dimension. |
| D5 | Chat UI: assistant-ui inside our Next.js app (built-in); LibreChat as an optional alternative front-end; Open WebUI not used on the live path | ✅ **Approved.** Both are MIT. Open WebUI's license requires keeping its branding above 50 users, and its own RAG and user model would bypass our permission pipeline. |

---

## 18. Changelog

| Version | Date | Changes |
|---|---|---|
| 1.0 | 2026-10-03 | First complete draft: requirements, NFRs, release plan, build contract (§17). Model choice moved to the install wizard. |
| 1.0.1 | 2026-10-04 | Operations gaps: environments (FR-RL6), upgrades and migrations (FR-F16), PII masking in traces (FR-O12), secret and certificate rotation (FR-F17), runbooks (FR-O13). |
| 1.1 | 2026-10-04 | Completeness pass. **Added:** user offboarding (FR-F18, US13), Lab reproducibility and cost estimates (FR-L2, FR-L4), trash and restore (FR-D9), malware scanning (FR-D14), data egress policy (FR-M9), bot access and knowledge scope (FR-RL7), conversation history (FR-C11), grounding and no-existence leaks (FR-C12), document search (FR-S10), retention defaults (NFR-10), mobile-responsive UI (NFR-13), application security (NFR-18), 3 risks, glossary terms. **Install tiers** (FR-F19, §12, US14): a Lite tier for solo developers on a laptop (Ollama or external APIs, single environment, local accounts, built-in tracing), built first in Phase 0. **Fixed:** wrong section references, FR-F ordering, "Why this answer?" priority conflict (FR-C9), release gates depending on risk tiers before those exist (FR-RL2), Keycloak and migrations added to Phase 0 scope. |
| 1.2 | 2026-10-04 | **Documents with images:** baseline tables, OCR, and figure crops in every tier (FR-D3); optional vision-model add-on for complex documents (FR-D15); technical and maintenance manual handling with verbatim safety warnings (FR-D16, US15); figure and table crops in citations (FR-R7); document-understanding test set (FR-T13); Lite-tier vision option; VLM misread risk. Q6 resolved. |
| 1.3 | 2026-10-04 | Job/workflow engine is selectable: Celery (default, every tier) or Temporal (Standard/Enterprise), behind one job interface (FR-F20). Docling confirmed as the parser in every tier; Unstructured and MinerU are only for Lab comparison. |
| 1.4 | 2026-10-05 | Exhaustive completeness sweep. **Added:** configuration as code (FR-F21), documentation deliverables (FR-F22), OCR language packs (FR-D3), version handling in retrieval (FR-D1), cross-lingual retrieval tests (FR-R8), spreadsheet questions as P3 (FR-R10), stop button (FR-C9), answer language (FR-C13), exit-friendly backups (NFR-6), no outbound telemetry (NFR-12), health endpoints (NFR-16), resilience and fail-closed permissions (NFR-19), API and data standards (NFR-20), developer setup, test strategy, CI/CD (§17.9–17.11). |
| 1.5 | 2026-10-05 | **Part II — Technical Design** (T1–T11): process list and Lite memory budget, code structure and the only ports, data model, permission design (OpenFGA plus `doc_principals` read-index, tighten-first rule, filtered pgvector query), key flows F1–F7, Lab adapter HTTP contract, API surface, config file, library choices, Phase 0 slice, decisions D1–D5. **Chat UI:** built-in with assistant-ui (FR-C14); LibreChat as an optional front-end through an OpenAI-compatible endpoint (FR-C15); Open WebUI excluded from the live path. |
