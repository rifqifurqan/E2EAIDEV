# E2EAIDEV — End-to-End Enterprise AI Development Lab

A self-hostable platform that teaches, and lets a company actually run, the **full enterprise AI development lifecycle**: plan → data → build → test → release → operate → improve.

It has two layers:

1. **The Lab (primary).** At every lifecycle stage, the tools enterprises actually use can be installed **side by side** and compared on the user's own data: their strengths, weaknesses, cost, and license. Example: run Ragas, DeepEval, Phoenix, and promptfoo on the same dataset and see which one agrees with human reviewers.
2. **The reference product: a permission-aware RAG chatbot.** Built with the Lab, it's an enterprise assistant where people upload and **share documents like Google Drive** (with a person, team, role, division, or the whole company). The AI only knows what each person is allowed to see, and it can query existing systems (ERP, HR, CRM) through their APIs.

> **Status:** planning. No code yet. Research done October 2026; re-check versions and licenses before each phase.
> **Out of scope for now:** omnichannel (WhatsApp, Slack, Teams). It will be added later as a channel layer on the same chatbot.

---

## 1. Goals and constraints

| Area | Decision |
|---|---|
| Purpose | Help people understand and practice end-to-end enterprise AI development by comparing real tools, and ship a production-grade RAG chatbot as the result. |
| Deployment | Self-hosted first. Docker Compose for dev and single-node installs, Helm/Kubernetes for prod. Must run **fully air-gapped** with local models. |
| Hardware | GPU optional. CPU installs use Ollama with small, quantized models; GPU installs turn on vLLM. |
| Tenancy | One company per install, with divisions, teams, roles, and users synced from the HR system or identity provider. SSO via OIDC. |
| Stack | Python 3.12 + FastAPI (API and workers), TypeScript + Next.js (UI), PostgreSQL as the system of record. |
| Principles | **Integrate, don't rebuild:** the platform is a control plane over best-in-class OSS tools. **Adapter per tool:** every tool sits behind a stable internal interface, so tools can be swapped and compared. **Isolate tools:** each Lab tool runs in its own container, because their dependencies conflict. **Fair comparison:** same data, same judge or model, same settings. |

---

## 2. How the Lab works

### 2.1 Install profiles ("pick what to install")
- **`core`:** the minimum to run the chatbot, with one default tool per stage. Light enough for a single CPU machine.
- **`lab-<stage>`:** extra tools for comparing one stage, for example `lab-eval`, `lab-vector`, `lab-parsing`, `lab-serving`.
- **`lab-all`:** everything, for training environments.
- **Install wizard (CLI + UI):**
  1. Detect GPU, RAM, and disk.
  2. Suggest a profile.
  3. Let the user tick which tools to install.
  4. Write `.env` and `values.yaml`.
  5. Pull pinned images.
  6. Download the models (air-gapped: from a local mirror).

### 2.2 Compare mode (the same pattern at every stage)
1. **Pick tools** that are installed for the stage.
2. **Fix the inputs:** same dataset, same documents, same judge or model through the gateway.
3. **Run:** each tool runs through its adapter, and results are normalized into a common schema.
4. **Report:**
   - **measured** results: quality, agreement with human labels, latency, cost, variance across repeated runs
   - **documented** results: what each tool's metric *really* means (the actual definition and the actual judge prompt), license, maturity, operational weight
5. **Learn:** each stage has "why this matters in enterprise" notes linked to standards such as OWASP, NIST, and the EU AI Act.

### 2.3 Learning layer
- **Guided scenarios**, for example *"Build an HR-policy bot end to end"* and *"Find out why your bot hallucinates"*. Each comes with sample data, expected results, and explanations at each stage.
- **Role-based paths:** AI engineer, evaluator/annotator, AI product manager, risk/compliance officer, platform/infra engineer.
- **Navigation follows the lifecycle** (Plan → Data → Build → Test → Release → Operate → Improve), so using the platform teaches the lifecycle.

---

## 3. Lifecycle stages and tool catalog

✅ = default in the `core` profile. Every other tool is available in the stage's `lab-*` profile.

### 3.1 Plan and govern
- **Use-case intake:** business case, success metrics (task success, deflection, time saved), feasibility.
- **AI risk classification:** EU AI Act risk tiers, the NIST AI Risk Management Framework, and ISO/IEC 42001 (AI management system). Each bot gets a risk tier, which decides its required release gates.
- **AI inventory:** every model and bot with its owner, risk tier, approval status, **model card**, and **system card**.

### 3.2 Data
| Need | Tools to compare | Default |
|---|---|---|
| Document storage (S3) | SeaweedFS (Apache 2.0), Garage (AGPL), RustFS, Ceph RGW. *MinIO CE is excluded: it went to maintenance mode in December 2025 and was archived in 2026.* | SeaweedFS ✅ |
| Parsing | Docling (MIT), Unstructured OSS (Apache 2.0), MinerU (AGPL, GPU, best on scanned PDFs) | Docling ✅ |
| Chunking | structure-aware, recursive by token count, semantic, parent-child | structure-aware ✅ |
| Dataset versioning and lineage | lakeFS, DVC | lakeFS (Phase 3) |
| Labeling and annotation | Label Studio, Argilla, built-in review queue | built-in ✅ |
| Synthetic test data | Ragas test-set generator, DeepEval Synthesizer, LLM persona-based generation | Ragas ✅ |
| PII discovery and redaction | Microsoft Presidio, GLiNER-based detectors | Presidio ✅ |

Data rules:
- **Deletion propagation:** deleting a source document removes its chunks, embeddings, caches, and any derived summaries.
- **Lineage:** every index version records which documents, parser, chunker, and embedding model produced it.

### 3.3 Build: models and serving
| Need | Tools to compare | Default |
|---|---|---|
| Model gateway | LiteLLM (MIT), Portkey (OSS gateway), Kong AI Gateway | LiteLLM ✅ |
| Serving | Ollama (CPU/dev), vLLM (GPU production), SGLang (agentic, multi-model), TensorRT-LLM (NVIDIA, large scale). *TGI is excluded: archived in 2026.* | Ollama ✅ (CPU) / vLLM ✅ (GPU) |
| Quantization | AWQ, GPTQ, GGUF (llama.cpp). Compare quality loss vs speed and memory. | GGUF for CPU ✅ |
| Fine-tuning (Phase 4) | Unsloth, Axolotl, TRL (LoRA/QLoRA, DPO), distillation from a big model into a small one | — |
| Model registry and experiment tracking | MLflow | MLflow (Phase 3) |

⚠️ **Supply chain:** in March 2026, LiteLLM PyPI releases 1.82.7 and 1.82.8 shipped a credential-stealing payload. Always use pinned, digest-verified images and hash-locked dependencies, and keep the gateway's secrets isolated.

### 3.4 Build: retrieval
| Need | Tools to compare | Default |
|---|---|---|
| Embedding model | BGE-M3 (MIT; dense + sparse, multilingual), Qwen3-Embedding 0.6B/4B/8B (Apache 2.0; tops MTEB multilingual), jina-embeddings-v3, e5, plus APIs (OpenAI, Cohere, Voyage). *NV-Embed-v2 is excluded: non-commercial license.* | BGE-M3 ✅ |
| Reranker | bge-reranker-v2-m3 (Apache 2.0), Qwen3-Reranker 0.6B/4B/8B (Apache 2.0), Cohere/Jina APIs, none | bge-reranker-v2-m3 ✅ |
| Vector store | Postgres + pgvector (hybrid search through full-text or `pg_search`), Qdrant (Apache 2.0), Weaviate (BSD-3), Milvus (Apache 2.0) | pgvector ✅ |
| Embedding/rerank serving | vLLM pooling runner (GPU), Infinity / TEI / Ollama (CPU) | Ollama ✅ (CPU) |
| RAG orchestration | Our own thin pipeline using LlamaIndex components; Haystack and LangChain as references. Reference platforms studied: RAGFlow, Onyx, Open WebUI. *Dify's license restricts multi-tenant use, so we don't build on it.* | own pipeline ✅ |
| Advanced RAG (Phase 4) | GraphRAG / knowledge graphs, multimodal (Qwen3-VL embeddings), query routing across knowledge bases | — |

What to compare:
- **Retrieval quality:** recall@k, MRR (how high the first correct document ranks), nDCG.
- **Indonesian and multilingual quality**, measured separately.
- **Speed and operations:** latency, index size, re-index time.

### 3.5 Build: prompts, agents, and tools
| Need | Tools to compare | Default |
|---|---|---|
| Prompt registry | Langfuse prompt management (MIT), MLflow Prompt Registry | Langfuse ✅ |
| Tool/API integration | MCP servers (one per system), with OpenAPI → MCP generation | MCP ✅ |
| Agent workflows (Phase 4) | LangGraph, LlamaIndex agents | — |
| Structured output | Native JSON mode, Guardrails AI validators, vLLM/SGLang guided decoding | native ✅ |

### 3.6 Test: the Eval Lab
| Framework | Strength | Weakness | License |
|---|---|---|---|
| **Ragas** ✅ | Best RAG retrieval metrics (faithfulness, context precision and recall) | Narrow outside RAG | Apache 2.0 |
| **DeepEval** | 50+ metrics, G-Eval custom judges, pytest-style CI | Code only, no UI | Apache 2.0 |
| **Arize Phoenix** | Tracing, embedding and retrieval visualizations, eval playground | Heavier; its license forbids offering it as a hosted service | Elastic License 2.0 |
| **promptfoo** | YAML prompt × model matrix, red-teaming | Limited depth on RAG metrics | MIT |
| Inspect AI | Capability and safety benchmarks | Less RAG-focused | MIT |

How the Eval Lab works:
- **Isolated adapters:** each framework runs in its own container (their dependencies conflict) behind `run(dataset, metrics, judge_model) → scores`.
- **Fair judging:** every framework uses the same judge model through LiteLLM, the same dataset and model outputs, and temperature 0.
- **Same name, different meaning:** for example, Ragas "faithfulness" checks each claim against the context, while Phoenix "hallucination" is a yes/no verdict. The UI shows each metric's definition and the judge prompt it sends, next to its score.
- **Evaluate the evaluators:** humans label a gold set, and each framework is ranked on agreement with humans (correlation, Cohen's κ), judge cost per 100 items, latency, and variance across 3 repeated runs.
- **Judging modes** per test suite:
  - **LLM-only:** one or more judges, with majority vote.
  - **Human-only:** items go to a review queue.
  - **Hybrid:** the LLM judges every item. An item goes to a human when judge confidence is low, when judges disagree, or when it falls in a random audit sample. Judge drift is tracked against human labels.

Other test types:

| Test type | Tools | Default |
|---|---|---|
| **Permission-leak tests** (see §4.2) | built-in persona suite | built-in ✅ |
| Security, OWASP Top 10 for LLM Applications (including indirect prompt injection via uploaded documents) | promptfoo red-team, garak | promptfoo ✅ |
| Safety and guardrails | NeMo Guardrails, Llama Guard 3, Guardrails AI. *LLM Guard is excluded: archived in July 2026.* | NeMo + Llama Guard ✅ |
| Bias and fairness | DeepEval bias metrics, custom persona sets | — |
| Load and performance | guidellm / LLMPerf (model endpoints), k6 / Locust (full chat API) | k6 ✅ |
| Standard benchmarks | lm-evaluation-harness | optional |
| Model benchmarking | Built-in runner: model × prompt × dataset leaderboard with quality, latency (p50/p95, time to first token), tokens/s, cost | built-in ✅ |

### 3.7 Release (CI/CD for AI)
- **The bot as a versioned bundle:** prompt version + model + retrieval config (embedding model, index version, reranker) + guardrails + tools. It is released and rolled back as one unit.
- **Release gates:** eval thresholds, zero permission leaks, red-team pass, and human sign-off for high-risk bots.
- **Rollout strategies:** shadow deploys (a new version answers silently alongside the current one), canary releases, online A/B tests with feature flags.

### 3.8 Operate
| Need | Tools to compare | Default |
|---|---|---|
| LLM tracing, cost, prompt analytics | Langfuse (MIT; acquired by ClickHouse in January 2026, still MIT and self-hostable), Arize Phoenix, MLflow 3 | Langfuse ✅ |
| Infra metrics and alerting | OpenTelemetry → Prometheus + Grafana | ✅ |
| Online evaluation | Langfuse evaluators on sampled production traffic | ✅ |
| Drift detection | Query-topic drift, embedding drift, quality decay as documents change | Phase 3 |
| User feedback | Thumbs up/down with an optional correction, attached to each trace | ✅ |
| FinOps | LiteLLM spend per team or division, budgets, chargeback | ✅ |
| GPU scheduling (Phase 4) | Kubernetes Kueue, NVIDIA MIG / time-slicing | — |
| AI incident management | Incident log, severity, linked traces, and the fix as a new release | Phase 3 |

### 3.9 Improve: the data flywheel
Production traces → bad answers flagged (thumbs-down, low online-eval score, human review) → curated into eval datasets or fine-tuning data → re-evaluated in the Eval Lab → released as a new bot bundle.

---

## 4. Reference product: permission-aware RAG chatbot

### 4.1 Sharing model ("Google Drive for knowledge")
- **Who can be shared with:** a person, a team, a role, a division, or the whole company.
- **Permission levels:**
  - **Owner:** share, delete
  - **Editor:** replace, re-upload
  - **Viewer:** read, and ask the AI about it
- **Folders and spaces:** sharing a folder shares its contents. Sharing can have an **expiry date** (for temporary project teams).
- **Implementation:** relationship-based access control with **OpenFGA** (Apache 2.0, CNCF), the same model as Google's Zanzibar. SpiceDB is the alternative to compare.
- **Org structure** (division, team, role) is synced from the HR system or identity provider over SCIM (Keycloak, Azure AD, Google Workspace). When someone moves divisions, their access changes automatically.

```
doc:wa-partnership.pdf  #owner   @user:you
doc:wa-partnership.pdf  #viewer  @user:andi
doc:wa-partnership.pdf  #viewer  @team:sales#member
team:sales              #member  @user:andi        ← synced from HR system
```

### 4.2 Permission-aware retrieval
**Rule: index each document once, filter by permission inside the query.** Never copy embeddings per user.

Example: you share a WhatsApp-partnership business PDF with Andi from Sales.
```
1. Upload → Docling parse → chunk → embed once → vector store (chunks keyed by document_id)
2. Share with Andi (viewer) → one OpenFGA relationship written; no re-embedding
   → Andi is notified: "You shared WA Partnership.pdf — ask the AI about it"
3. Andi asks "What's the revenue share in the WhatsApp partnership?"
   → resolve Andi's readable documents (own + shared + team/role/division + company-wide)
   → vector search filtered to those documents → rerank → answer with citation [WA Partnership.pdf, p.4]
4. Access revoked → the document is excluded from Andi's very next query
```

**Chat scopes** the user can pick: this document only / my documents / shared with me / my team / everything I can access.

**Leak paths and their fixes** (each one has a test in the permission-leak suite):

| Leak path | Fix |
|---|---|
| Filtering *after* top-k retrieval | Filter inside the vector query. With pgvector this is a SQL join on the access table, which is a key reason pgvector is the default. |
| Semantic cache serves an answer built from a forbidden document | Key the cache on the user's permission set, or cache per user only. |
| Derived content (summaries, knowledge graphs, team insights) | It inherits the *strictest* permissions of its sources. |
| Chat history after access is revoked | Hide citations from revoked sources and show a "source no longer accessible" notice. |
| Prompt injection hidden in a shared document | Treat retrieved text as data, scan on upload, and run guardrails on retrieved context. |

### 4.3 Connecting existing systems (ERP, HR, CRM)
| | Knowledge connectors | Live system tools |
|---|---|---|
| For | Documents: Google Drive, SharePoint/OneDrive, Nextcloud, Confluence | Data and actions: ERP, HR, CRM |
| How | Sync files into RAG, **mirroring the source system's permissions** | **Call the API at question time** through MCP. This data isn't copied into vectors, because it goes stale and its permissions are too complex. |
| Example | "Summarize the Q3 sales SOP" | "How many leave days do I have left?" → HR API. "Status of PO-1234?" → ERP API. |

- **Act as the real user:** the AI calls APIs *as the asking employee* through an OAuth token exchange, never with a super-admin account. The source system enforces its own permissions.
- **Read-only first.** Write actions (for example, submitting a leave request) need explicit user confirmation and are written to the audit log.
- **Admin flow:** register a system → upload its OpenAPI spec → choose allowed endpoints → configure auth → test in the playground → grant to roles or divisions.
- **Combined answers:** *"Per WA Partnership.pdf (p.4), revenue share is 70/30; the ERP shows 3 open invoices with that partner."*

### 4.4 Later: omnichannel
WhatsApp Business, Slack, Teams, and an embeddable web widget. Each is a channel adapter on the same chatbot API, and each needs to link the channel account (phone number, Slack ID) to an employee identity so permissions still apply. Not in the current roadmap.

---

## 5. Architecture

```
                 ┌──────────────────────────────────────────────────────────┐
 Users ─ SSO ───▶│ Web UI (Next.js)                                          │
                 │ Lifecycle nav: Plan · Data · Build · Test · Release ·     │
                 │ Operate · Improve  |  Chat · My Docs · Shared with me     │
                 └───────────────────────────┬──────────────────────────────┘
                                             │ REST/SSE
                 ┌───────────────────────────▼──────────────────────────────┐
                 │ Control Plane API (FastAPI)                               │
                 │ projects · bot bundles · registries · install profiles ·  │
                 │ jobs · audit log · notifications                          │
                 └──┬─────────┬──────────┬──────────┬──────────┬────────────┘
                    │         │          │          │          │
        ┌───────────▼──┐ ┌────▼──────┐ ┌─▼────────┐ ┌▼────────┐ ┌▼────────────────┐
        │ Knowledge &  │ │ Ingestion │ │ Chat /   │ │ Lab     │ │ Tool Gateway    │
        │ Sharing svc  │ │ workers   │ │ RAG      │ │ runners │ │ (MCP servers,   │
        │ (OpenFGA)    │ │ connectors│ │ runtime  │ │ eval,   │ │ OAuth token     │
        │ ◀─ SCIM from │ │ parse,    │ │ ACL-     │ │ bench,  │ │ exchange) ──▶   │
        │ HR system    │ │ chunk,    │ │ filtered │ │ compare │ │ ERP · HR · CRM  │
        └──────────────┘ │ embed     │ │ retrieve,│ │ (1 ctr  │ └─────────────────┘
                         └──┬────────┘ │ rerank,  │ │ per tool)│
                            │          │ guards,  │ └────┬────┘
                            │          │ generate │      │
                            │          └──┬───────┘      │
            ┌───────────────▼─┐   ┌───────▼──────────────▼──┐   ┌─────────────────┐
            │ Object storage  │   │ LiteLLM gateway          │   │ Vector store    │
            │ (SeaweedFS/S3)  │   │ keys · budgets · routing │   │ pgvector ✅ /   │
            └─────────────────┘   └──┬─────────┬─────────┬───┘   │ Qdrant/Weaviate │
                                     │         │         │       │ /Milvus (lab)   │
                                ┌────▼──┐ ┌────▼──┐ ┌────▼─────┐ └─────────────────┘
                                │ vLLM  │ │Ollama │ │ External │
                                │ (GPU) │ │ (CPU) │ │ APIs     │
                                └───────┘ └───────┘ └──────────┘

 Cross-cutting: PostgreSQL (system of record) · Redis (queue/cache) · Langfuse (traces,
 prompts, scores) · OpenTelemetry → Prometheus/Grafana · Vault/K8s secrets · Keycloak (optional)
```

### Core domain model (Postgres)
- `Org → Division → Team → User(roles)`, synced from HR or the identity provider.
- `Folder/Space → Document(owner, versions, source, lineage) → Chunk(document_id)`. Sharing relationships live in OpenFGA.
- `KnowledgeIndex(embedding_model, dim, chunker, vector_store, version)`
- `Bot bundle(prompt_ref, model, index_version, reranker, guardrails, tools, version, risk_tier)`
- `ToolConnection(system, openapi_spec, allowed_endpoints, auth, granted_to)`
- `Dataset → Item`, `EvalSuite(rubric, judge_mode, frameworks[])`, `EvalRun → Result → HumanReview`, `ComparisonReport`
- `AIInventoryEntry(model/bot, owner, risk_tier, model_card, approval)`, `Incident`, `Feedback`

### Security baseline
- OIDC SSO, RBAC for platform features, OpenFGA for document access, and an audit log for every share, query, and tool call.
- Secrets in Vault or Kubernetes secrets, never in plaintext in the database.
- Supply chain: pinned image digests, hash-locked dependencies, SBOM and dependency scanning in CI, model files as safetensors (scan pickle files).
- Encryption at rest, data-retention policies for traces and chats, and PII redaction (Presidio).

---

## 6. Roadmap (phases follow the lifecycle)

### Phase 0: Foundations (≈2 weeks)
- Monorepo (`apps/api`, `apps/web`, `workers/`, `adapters/`, `deploy/compose`, `deploy/helm`), CI, pinned dependencies.
- `core` Compose profile: Postgres, Redis, LiteLLM, SeaweedFS, Langfuse, Ollama, OpenFGA.
- OIDC auth, org structure (divisions, teams, roles; manual entry first, SCIM in Phase 3).
- The adapter interface pattern, defined once and reused by every Lab stage.

### Phase 1: MVP, "permission-aware RAG chatbot built and evaluated in the Lab" (≈8 weeks)
- **Data:** upload, Docling parsing, structure-aware chunking, BGE-M3, pgvector hybrid search.
- **Sharing:** folders, sharing with a user, team, role, division, or company, viewer/editor/owner levels, notifications.
- **Chat:** permission-filtered retrieval, bge-reranker-v2-m3, citations, chat scopes, streaming, Langfuse traces, thumbs feedback.
- **Prompt registry** through Langfuse. **Bot as a versioned bundle.**
- **Test:** synthetic Q&A generation, Ragas with an LLM judge, the **permission-leak persona suite**, run-vs-run comparison.
- **Done when:** on one CPU machine, a user uploads a PDF, shares it with Andi, and Andi asks about it and gets a cited answer; a user who wasn't given access gets nothing; and an eval run produces scores.

### Phase 2: Eval Lab and Build Lab (≈6 weeks)
- **Eval Lab:** DeepEval, Phoenix, and promptfoo adapters, the human review queue, hybrid judging, the human gold set, and the evaluate-the-evaluators report.
- **Benchmark runner:** model × prompt × dataset leaderboard (quality, latency, cost).
- **Retrieval Lab:** Qdrant vs pgvector, BGE-M3 vs Qwen3-Embedding, reranker on vs off, a separate Indonesian retrieval set.
- **Serving:** vLLM GPU profile. Ollama vs vLLM comparison.
- **Live tools v1:** an MCP gateway, OpenAPI → tool, read-only HR/ERP calls made as the real user.
- **Release gates** in CI (eval thresholds, zero leaks).

### Phase 3: Enterprise readiness (≈6–8 weeks)
- **Data:** Google Drive, SharePoint, Nextcloud, and Confluence connectors with permission mirroring. SCIM sync from the HR system or identity provider. lakeFS lineage. Deletion propagation. Parsing Lab (Docling vs Unstructured vs MinerU).
- **Test:** guardrails stage (NeMo + Llama Guard), red-teaming (promptfoo, garak), load testing (k6, guidellm).
- **Release and operate:** shadow and canary rollouts, online evals, drift detection, incident log, FinOps per division.
- **Govern:** AI inventory, risk tiers, model and system cards, approval workflows. MLflow model registry.
- **Deploy:** Helm chart, install wizard, air-gapped bundle (image tarballs plus a model mirror). Backup and disaster recovery.

### Phase 4: Advanced (ongoing)
- Fine-tuning and distillation (Unsloth, Axolotl, TRL) and a quantization comparison lab, all feeding back into benchmarking.
- Agents (LangGraph) with agent-trajectory evaluation. Live-tool write actions with user confirmation.
- GraphRAG, multimodal RAG, SGLang and TensorRT-LLM engines, GPU scheduling (Kueue, MIG).
- Omnichannel adapters (WhatsApp Business, Slack, Teams, web widget).
- Guided scenarios and role-based learning paths across every stage.

### Key risks
| Risk | Mitigation |
|---|---|
| Too many tools, so it's heavy to install and slow to build | A light `core` profile; `lab-*` profiles are opt-in; adapters are added stage by stage. |
| Adapter maintenance as tool APIs change | Pinned versions, nightly smoke test per adapter, an adapter contract test suite. |
| Permission leaks in RAG | Filtering inside the query, a leak test suite as a release gate, strictest-permission inheritance for derived data. |
| LLM-judge bias and drift | Hybrid judging, a human gold set, judge-agreement monitoring. |
| License traps (AGPL MinerU/Garage, Phoenix ELv2, NC models, Dify) | License shown in the tool catalog and checked at install time; AGPL tools run as separate services. |
| Supply-chain compromise | Pinned digests and hashes, SBOM, isolated gateway secrets. |
| Langfuse (ClickHouse) is heavy on small installs | Measure on the CPU profile; allow a Postgres-only tracing fallback. |

---

## 7. Sources

- Evaluation: [Confident AI – LLM eval tools 2026](https://www.confident-ai.com/knowledge-base/compare/best-llm-evaluation-tools), [FutureAGI – OSS eval frameworks 2026](https://futureagi.com/blog/best-open-source-eval-frameworks-2026/), [DeepEval – Top 5 frameworks](https://deepeval.com/blog/top-5-llm-evaluation-frameworks)
- Gateway: [Requesty – LLM routing platforms 2026](https://www.requesty.ai/blog/best-llm-routing-platforms-compared-2026-requesty-portkey-litellm-openrouter), [Spheron – LiteLLM/Portkey/Kong](https://www.spheron.network/blog/ai-gateway-litellm-portkey-kong-gpu-cloud/), [LiteLLM security update (Mar 2026)](https://docs.litellm.ai/blog/security-update-march-2026), [Datadog – LiteLLM compromise analysis](https://securitylabs.datadoghq.com/articles/litellm-compromised-pypi-teampcp-supply-chain-campaign/)
- Serving: [vLLM vs SGLang vs Ollama 2026](https://stackpulsar.com/blog/vllm-sglang-ollama-comparison/), [Swfte – serving frameworks 2026](https://www.swfte.com/blog/llm-serving-frameworks-2026-comparison), [TensorFoundry – inference servers compared](https://tensorfoundry.io/blog/llm-inference-servers-compared)
- Observability: [MLflow – LLM observability tools 2026](https://mlflow.org/articles/top-llm-observability-tools-in-2026-a-pro-guide/), [Langfuse vs Phoenix](https://myengineeringpath.dev/tools/langfuse-vs-phoenix-arize/), [ClickHouse acquires Langfuse](https://clickhouse.com/blog/clickhouse-acquires-langfuse-open-source-llm-observability)
- Parsing: [MinerU vs Docling vs Marker](https://builderai.tools/blog/pdf-parsing-for-rag-mineru-docling-marker-compared), [Document parsing for production RAG](https://medium.com/@manikandan_t/document-parsing-for-production-rag-architecture-tradeoffs-and-when-to-use-what-7a89ab0af7b7)
- Embeddings and rerankers: [Qwen3 Embedding paper](https://arxiv.org/pdf/2506.05176), [PremAI – embedding models for RAG 2026](https://www.premai.io/blog/best-embedding-models-for-rag-2026-ranked-by-mteb-score-cost-and-self-hosting/), [Best OSS embedding and reranker models 2026](https://builderai.tools/blog/best-open-source-embedding-models-2026)
- Vector DBs: [Firecrawl – best vector databases](https://www.firecrawl.dev/blog/best-vector-databases), [KKRF – vector DBs for enterprise RAG](https://kkrfgroup.com/vector-database-comparison-enterprise-rag/)
- Object storage: [MinIO CE in 2026](https://www.glukhov.org/data-infrastructure/object-storage/minio-dead/), [Best MinIO alternatives 2026](https://dev.to/ethan-carter/best-minio-alternatives-in-2026-6-options-that-actually-work-17p2)
- Guardrails: [Guardrails AI vs NeMo vs LLM Guard](https://kanopylabs.com/blog/guardrails-ai-vs-nemo-guardrails-vs-llm-guard), [NeMo vs Llama Guard vs Guardrails AI](https://particula.tech/blog/ai-guardrails-compared-nemo-guardrails-ai-llama-guard)
- RAG platforms: [Jimmy Song – Dify, RAGFlow, LangGraph compared](https://jimmysong.io/blog/open-source-ai-agent-workflow-comparison/), [Open WebUI vs Dify](https://docs.openwebui.com/alternatives/dify/)
