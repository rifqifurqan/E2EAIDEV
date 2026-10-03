# E2EAIDEV — End-to-End AI Development Platform

A self-hostable platform that lets a company run the whole AI development lifecycle in one place: prompt engineering, model benchmarking, automated evaluation (LLM-as-a-judge, human, or hybrid), a RAG chatbot builder, pluggable model serving, and observability.

> **Status:** planning. This document holds the research, architecture, and roadmap. No code yet.
> Research was done in October 2026. Re-check the versions and licenses before Phase 1 starts.

---

## 1. Goals and constraints

| Area | Decision |
|---|---|
| Deployment | Self-hosted first. Docker Compose for dev and single-node installs, Helm/Kubernetes for prod. Must run **fully air-gapped** with local models only. |
| Hardware | GPU optional. CPU installs use Ollama with small models; GPU installs can turn on vLLM. |
| Tenancy | One company per install, with workspaces, projects, RBAC, and SSO (OIDC). |
| Stack | Python 3.12 + FastAPI (API and workers), TypeScript + Next.js (UI), PostgreSQL as the system of record. |
| Principle | **Integrate, don't rebuild.** The platform is a *control plane* that configures and orchestrates best-in-class OSS components behind stable internal interfaces, so each component can be swapped. |

---

## 2. State-of-the-art research by lifecycle stage

Each stage compares the leading options and recommends one default. "Pluggable" means users can pick another option at install time.

### 2.1 Model gateway (one API for every model)

| Option | License | Notes |
|---|---|---|
| **LiteLLM** ✅ | MIT | The most widely adopted self-hosted gateway. OpenAI-compatible API over 100+ providers, including vLLM and Ollama. Virtual keys, budgets, cost tracking, fallbacks. |
| Portkey | OSS gateway + commercial | Stronger guardrails and governance, but the full feature set lives in the managed cloud. |
| Kong AI Gateway | OSS + enterprise | Only makes sense if Kong already runs your API mesh. |

**Recommendation: LiteLLM proxy**, deployed from a **pinned, digest-verified container image**.
⚠️ In March 2026, LiteLLM PyPI releases 1.82.7 and 1.82.8 were compromised in a supply-chain attack (credential-stealing `.pth` payload). Rules for us:
- Never `pip install litellm` unpinned.
- Pin hashes and scan dependencies in CI.
- Keep the gateway's secrets isolated from other services.

### 2.2 Model serving

| Option | Best for | Notes |
|---|---|---|
| **vLLM** ✅ (GPU) | Multi-user production serving | The most widely deployed engine with the broadest hardware support. PagedAttention and continuous batching. Also serves embedding and reranker models. |
| SGLang | Agentic / structured-output workloads, many models at once | Often faster than vLLM in H100 benchmarks; RadixAttention shares KV cache. Planned as an optional engine. |
| **Ollama** ✅ (CPU/dev) | Local, edge, CPU-only installs | The easiest setup and the widest hardware support. Not built for high-concurrency production. |
| TGI | — | ❌ Hugging Face put it in maintenance mode in December 2025, and the repo was archived in 2026. Don't use it for new builds. |
| TensorRT-LLM + Triton | 100+ concurrent users, NVIDIA only | Phase 4+ option for large installs. |

**Recommendation:** Ollama for CPU and dev profiles, vLLM for GPU profiles. Both sit behind LiteLLM, so apps never talk to an engine directly.

### 2.3 Prompt engineering and management

| Option | License | Notes |
|---|---|---|
| **Langfuse prompt management** ✅ | MIT | Versioned prompts, labels (`production`/`staging`), playground, prompt experiments over datasets. It's already part of the observability stack. |
| MLflow Prompt Registry | Apache 2.0 | Good if you already run MLflow for classic ML. |
| Build our own | — | Not worth it for the MVP. |

**Recommendation:** use Langfuse as the prompt registry. Our UI adds A/B test orchestration on top: run prompt versions × models × dataset, then compare scores.

### 2.4 Evaluation (automated testing, LLM-as-a-judge, human, hybrid)

| Option | Strength |
|---|---|
| **Ragas** ✅ | Best RAG-specific metrics: faithfulness, context precision and recall, answer relevance. |
| **DeepEval** ✅ | Broadest metric library (50+), pytest-style CI integration, G-Eval custom judges. |
| **promptfoo** ✅ | YAML prompt × model matrices, plus **red-teaming** (prompt injection, jailbreak, PII leakage). |
| Inspect AI | Strong for capability and safety benchmarks. Optional. |
| Arize Phoenix | Strong for RAG debugging and embedding visualization. Optional add-on. |

**Recommendation:** our own **Eval Runner** service that calls Ragas and DeepEval metrics as libraries and promptfoo for red-team suites, then writes every score to Postgres and Langfuse.

**Judging modes** (configured per test suite):
1. **LLM-only**: a judge model scores with a rubric (G-Eval style). Supports multiple judges and majority vote.
2. **Human-only**: items go to an annotation queue (Langfuse annotation queues, or our UI).
3. **Hybrid**:
   - The LLM judges every item.
   - An item goes to the human queue when any of these is true:
     - judge confidence is below a threshold
     - two judges disagree
     - the item falls in a random X% audit sample
   - Human labels are used to **calibrate the judge**: track the agreement rate and Cohen's κ per rubric, and alert when the judge drifts.

### 2.5 Model benchmarking

- **Custom benchmarks:** the user's own datasets, run through the Eval Runner. Report quality, latency (p50/p95, TTFT), tokens/s, and $/1k requests, using cost data from LiteLLM.
- **Standard benchmarks (optional):** EleutherAI `lm-evaluation-harness` for academic suites (MMLU and similar). For throughput, use vLLM's built-in benchmark tools.
- Output is a leaderboard per project: model × prompt version × dataset.

### 2.6 Document storage (file management)

| Option | License | Notes |
|---|---|---|
| MinIO CE | AGPLv3 | ❌ Community edition went to maintenance mode in December 2025, and the repo became read-only in April 2026. Avoid it for new builds. |
| **SeaweedFS** ✅ | Apache 2.0 | S3-compatible, light enough for a single node, scales out. Apache 2.0 makes redistribution easy. |
| Garage | AGPLv3 | A very good small-cluster default, but AGPL. |
| RustFS | Apache 2.0 | Newer project; write-heavy single-node workloads. Watch its maturity. |
| Ceph RGW | LGPL | For large enterprises that already run Ceph. |

**Recommendation:** SeaweedFS as the built-in S3 store, shared with Langfuse for payload storage. Users can point at any S3-compatible endpoint instead (AWS S3, Ceph, Garage).
For a user-facing file manager, add **connectors** rather than embedding a file manager: S3 bucket, Nextcloud (WebDAV), SharePoint/OneDrive, Google Drive, and Confluence. Connectors sync on a schedule into the ingestion pipeline.

### 2.7 Document parsing and chunking

| Option | License | Notes |
|---|---|---|
| **Docling** ✅ | MIT (LF AI & Data) | IBM Research. Layout-aware PDF/DOCX/PPTX → structured Markdown/JSON with tables. Runs well on CPU (~3 s/page). |
| MinerU | AGPL-3.0 | Best on scanned PDFs and complex tables using VLM layout analysis. Needs a GPU. Optional, and AGPL, so it runs as a separate service. |
| Unstructured (OSS) | Apache 2.0 | Widest format coverage (25+, including email and HTML), but weaker tables and the slowest on CPU. Used as a fallback for formats Docling doesn't handle. |

**Recommendation:** Docling by default, Unstructured as fallback for other formats, and MinerU as an optional GPU route for scanned documents.
**Chunking strategies (user-selectable):** structure-aware (headings and sections, default), recursive by token count, semantic, and parent-child (small chunks for retrieval, return the parent).

### 2.8 Embedding models (user-selectable)

| Model | License | Notes |
|---|---|---|
| **Qwen3-Embedding (0.6B / 4B / 8B)** ✅ | Apache 2.0 | Top of MTEB multilingual (8B ≈ 70.6). The 0.6B model fits CPU installs. |
| **BGE-M3** ✅ | MIT | Most downloaded. Returns **dense + sparse + multi-vector** in one model, which is good for hybrid search. Strong multilingual support, including Indonesian. |
| NV-Embed-v2 | CC-BY-NC | Top of MTEB English, but **non-commercial license**. Exclude it by default. |
| jina-embeddings-v3, e5 family | varies | Alternatives. |
| OpenAI / Cohere / Voyage APIs | commercial | Through LiteLLM, for non-air-gapped installs. |

**Recommendation:** BGE-M3 as the default (hybrid-friendly, MIT), Qwen3-Embedding for best accuracy. Serve them with vLLM's pooling runner on GPU, or with Infinity/TEI or Ollama on CPU.
**Rule:** an index is bound to its embedding model and dimension. Changing the model means re-indexing, handled as a versioned background job.

### 2.9 Rerankers (user-selectable)

| Model | License | Notes |
|---|---|---|
| **bge-reranker-v2-m3** ✅ | Apache 2.0 | Light, multilingual, a CPU-friendly default. |
| **Qwen3-Reranker (0.6B / 4B / 8B)** ✅ | Apache 2.0 | Most accurate open reranker in 2026, with 32K context. |
| Cohere Rerank / Jina Reranker API | commercial | Through the API for non-air-gapped installs. |
| None | — | Allowed, for latency-sensitive bots. |

### 2.10 Vector store (user-selectable at install)

| Option | License | Notes |
|---|---|---|
| **Postgres + pgvector** ✅ | PostgreSQL | No extra database to run, and it can join with relational data (ACLs, metadata). Fine up to roughly 10–50M vectors. Hybrid search comes from Postgres full-text or BM25 through `pg_search`/ParadeDB. |
| **Qdrant** ✅ | Apache 2.0 | Fast (Rust), excellent payload filtering, native sparse vectors and hybrid search. The scale-up choice. |
| Weaviate | BSD-3 | Strongest built-in hybrid search and multi-tenancy. |
| Milvus | Apache 2.0 | Billion-scale, but heavier to operate. |

**Recommendation:** pgvector by default, Qdrant as the scale-up option. Both sit behind a `VectorStore` interface, so Weaviate and Milvus can be added later.

### 2.11 RAG orchestration

- **Frameworks:** LlamaIndex (strongest ingestion and indexing primitives) or Haystack (clean pipelines). LangChain/LangGraph for agentic flows.
  **Recommendation:** keep our own thin pipeline layer (retrieve → rerank → assemble context → generate → cite) and use LlamaIndex components inside it, so we aren't locked into a framework.
- **Reference platforms studied:**
  - **RAGFlow** (Apache 2.0): deep document understanding and citations.
  - **Dify:** visual builder. Its modified license restricts multi-tenant use, so we don't build on it.
  - **Open WebUI:** chat UX.
- **Retrieval features:**
  - hybrid search (dense + sparse/BM25 with RRF fusion)
  - metadata filters
  - document-level ACL filtering (users only retrieve what they're allowed to read)
  - query rewriting
  - citations with page and section anchors

### 2.12 Guardrails and safety

| Option | License | Notes |
|---|---|---|
| **NeMo Guardrails** ✅ | Apache 2.0 | Input, dialog, retrieval, execution, and output rails (Colang). |
| **Llama Guard 3 / similar safety classifiers** ✅ | Llama license | Content-safety classification, served through vLLM or Ollama. |
| Guardrails AI | Apache 2.0 | Structured-output validation (validator hub). |
| LLM Guard (Protect AI) | MIT | ⚠️ Repo archived in July 2026. Treat it as frozen. |

**Recommendation:** a guardrail stage in the chat pipeline: PII redaction, prompt-injection detection, safety classification, and output validation. promptfoo red-team suites run in CI before a bot is published.

### 2.13 Observability

| Option | License | Notes |
|---|---|---|
| **Langfuse** ✅ | MIT | The most widely adopted OSS LLM observability tool: traces, costs, prompt management, datasets, LLM-as-a-judge, annotation queues. Self-hosting and air-gapped installs are first-class. ClickHouse acquired it in January 2026; the MIT license and self-hosting stay. Needs ClickHouse, Redis, and S3. |
| Arize Phoenix | Elastic License 2.0 | Best for RAG and embedding debugging. Optional add-on. |
| MLflow 3 | Apache 2.0 | A strong end-to-end GenAI lifecycle option if MLflow is already the standard. |

**Recommendation:** Langfuse plus **OpenTelemetry** for the platform's own services (Prometheus + Grafana for infra metrics).

---

## 3. Architecture

### 3.1 Components

```
                        ┌────────────────────────────────────────────┐
  Users / SSO (OIDC) ──▶│  Web UI (Next.js)                          │
                        │  Prompts · Benchmarks · Evals · RAG Builder│
                        │  Chat Playground · Admin/Install           │
                        └──────────────────┬─────────────────────────┘
                                           │ REST/SSE
                        ┌──────────────────▼─────────────────────────┐
                        │  Control Plane API (FastAPI)               │
                        │  auth/RBAC · projects · registries ·       │
                        │  provider config · job scheduling          │
                        └───┬──────────┬───────────┬─────────────┬───┘
                            │          │           │             │
               ┌────────────▼──┐ ┌─────▼──────┐ ┌──▼─────────┐ ┌─▼──────────────┐
               │ Ingestion     │ │ Eval Runner│ │ RAG Runtime│ │ Benchmark      │
               │ Workers       │ │ (Ragas,    │ │ (retrieve, │ │ Runner         │
               │ (connectors,  │ │ DeepEval,  │ │ rerank,    │ │ (latency/cost/ │
               │ Docling,      │ │ promptfoo) │ │ guardrails,│ │ quality)       │
               │ chunk, embed) │ │            │ │ generate)  │ │                │
               └──┬─────┬──────┘ └─────┬──────┘ └──┬─────┬───┘ └───────┬────────┘
                  │     │              │           │     │             │
                  │     └──────────────┴─────┬─────┘     │             │
                  │                          │           │             │
     ┌────────────▼───┐  ┌───────────────────▼──┐  ┌─────▼────────┐    │
     │ Object Storage │  │ LiteLLM Gateway      │◀─┤ Vector Store │    │
     │ (SeaweedFS/S3) │  │ keys·budgets·routing │  │ pgvector |   │    │
     └────────────────┘  └───┬────────┬─────┬───┘  │ Qdrant       │    │
                             │        │     │      └──────────────┘    │
                       ┌─────▼──┐ ┌───▼──┐ ┌▼──────────────┐           │
                       │ vLLM   │ │Ollama│ │External APIs  │◀──────────┘
                       │ (GPU)  │ │(CPU) │ │(OpenAI, etc.) │
                       └────────┘ └──────┘ └───────────────┘

  Cross-cutting: PostgreSQL (system of record) · Redis (queue/cache)
                 Langfuse (traces, prompts, scores) · OTel → Prometheus/Grafana
```

### 3.2 Key data flows

1. **Ingest:**
   - Connector sync → raw file to S3 → Docling parse → chunk.
   - Embed (selected model through LiteLLM or vLLM) → upsert into the vector store with ACL metadata.
   - Record the version in Postgres.
2. **Chat (RAG):**
   - Query → input guardrails → query rewrite → hybrid retrieve (ACL-filtered).
   - Rerank → assemble context → LLM through LiteLLM → output guardrails → answer with citations.
   - Full trace to Langfuse.
3. **Eval:**
   - Dataset × (prompt version, model, RAG config) → run → judges (LLM, human, or hybrid).
   - Scores go to Postgres and Langfuse. A regression gate decides whether a release passes.
4. **Benchmark:** the same runner as Eval, plus latency/throughput sampling and cost from LiteLLM spend logs.

### 3.3 Core domain model (Postgres)

`Workspace → Project → { PromptRef, Dataset(Item), EvalSuite(Rubric, JudgeConfig), EvalRun(Result, HumanReview), KnowledgeBase(Source, Document, IndexVersion{embedding_model, dim, chunking, vector_store}), Bot(kb_ids, prompt_ref, model, reranker, guardrails, version), ProviderConfig(model endpoints, keys via secret store) }`

### 3.4 "Pick what to install": modular deployment

- **Docker Compose profiles:** `core` (api, ui, postgres, redis, litellm, seaweedfs, langfuse) plus optional `qdrant`, `ollama`, `vllm`, `mineru`, `phoenix`, `monitoring`.
  Example: `docker compose --profile core --profile qdrant --profile vllm up -d`.
- **Install wizard (CLI + UI):**
  1. Detect GPU, RAM, and disk.
  2. Suggest a profile (CPU-lite / GPU-standard / enterprise).
  3. Write `.env` and `values.yaml`.
  4. Pull pinned images.
  5. Download the selected models (air-gapped: from a local model mirror).
- **Helm chart** for Kubernetes, with the same toggles as values flags. vLLM runs as a GPU node-pool deployment.

### 3.5 Security baseline

- OIDC SSO (Keycloak bundled optionally), RBAC per workspace and project, audit log.
- Secrets in a secret store (Vault or Kubernetes secrets); never in plaintext in Postgres.
- Document-level ACLs enforced *at retrieval time*, not just in the UI.
- Supply chain:
  - pinned image digests and lockfiles with hashes
  - SBOM and dependency scanning in CI
  - see the LiteLLM incident above
- PII redaction on ingestion (optional) and in guardrails. Data retention policies for traces.

---

## 4. MVP scope and phased roadmap

### Phase 0: Foundations (≈2 weeks)
- Monorepo (`apps/api`, `apps/web`, `workers/`, `deploy/compose`, `deploy/helm`), CI, lint/test, pinned dependencies.
- Compose `core` profile up: Postgres, Redis, LiteLLM, SeaweedFS, Langfuse, Ollama.
- Auth (OIDC), workspaces and projects, provider config (add a model endpoint through LiteLLM).

### Phase 1: MVP, "RAG chatbot with evals" (≈6–8 weeks)
- **RAG builder:** S3/upload source → Docling → structure-aware chunking → BGE-M3 → pgvector (hybrid) → bge-reranker-v2-m3 → chat with citations.
- **Chat playground** with model, prompt, and RAG-config pickers. Streaming. Traced in Langfuse.
- **Prompt registry** through Langfuse, linked into bots.
- **Eval v1:** datasets (upload CSV/JSONL or generate synthetic Q&A from a KB), LLM-as-a-judge with Ragas metrics plus a custom rubric, a results table, and a comparison of two runs.
- **Done when:** a user can install on one CPU machine, upload documents, publish a bot, and run an eval suite with scores.

### Phase 2: Hybrid evaluation and benchmarking (≈4–6 weeks)
- Human review queue and the hybrid judge (confidence and disagreement routing, audit sampling, judge-agreement metrics).
- Benchmark runner: model × prompt × dataset leaderboard with latency, throughput, and cost.
- DeepEval metrics and a CI regression gate (fail the bot release if scores drop).
- vLLM GPU profile. Qdrant option. Qwen3 embedding and reranker options with re-index jobs.

### Phase 3: Enterprise readiness (≈6 weeks)
- Connectors: Nextcloud (WebDAV), SharePoint/OneDrive, Google Drive, Confluence. Scheduled sync. Document-level ACL sync.
- Guardrails stage (NeMo Guardrails + safety classifier) and promptfoo red-team suites.
- Helm chart, install wizard, air-gapped bundle (image tarballs plus a model mirror).
- Audit log, retention policies, SSO group → role mapping.

### Phase 4: Scale and advanced (ongoing)
- SGLang / TensorRT-LLM engines, multi-GPU scheduling, autoscaling.
- Agentic bots (tools, LangGraph), MinerU scanned-document path, multimodal (Qwen3-VL embeddings).
- Fine-tuning hooks (LoRA through Unsloth/Axolotl) feeding back into benchmarking.

### Key risks
| Risk | Mitigation |
|---|---|
| Too many pluggable options too early | Ship one default per stage in the MVP and add options behind the interfaces later. |
| Operational weight of Langfuse (ClickHouse) on small installs | Measure on the CPU-lite profile; keep Langfuse optional, with traces falling back to Postgres. |
| LLM-judge bias and drift | Hybrid mode, human calibration sets, judge-agreement monitoring. |
| License traps (AGPL MinerU/Garage, NC embedding models, Dify) | Keep a license check in the model and component registry; run AGPL components as separate services only. |
| Supply-chain compromise | Pinned digests and hashes, SBOM, isolated gateway secrets. |

---

## 5. Sources

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
