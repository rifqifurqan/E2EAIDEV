# Ragas Lab adapter

The first **real** Lab tool (PRD T6). It is a small HTTP service in its own Python environment: the platform never imports
Ragas, and this service never imports the platform. Other tools (DeepEval, Phoenix, promptfoo, ...) follow the same shape,
so their scores can be compared on the same data with the same judge (FR-T3, FR-T12).

| Endpoint | What it does |
|---|---|
| `GET /info` | name, version, license, stage, operations, metrics, and **what each score means** (shown next to the score, FR-T4) |
| `GET /health` | liveness |
| `POST /run` | `{run_id, inputs[{item_id, question, answer, contexts[], ground_truth}], config{metrics[]}, judge{base_url, model, api_key, embedding_model}}` → `{rows[], errors[]}` |

Metrics: `faithfulness`, `answer_relevancy`, `context_precision`, `context_recall` (the last two need a reference answer).

Rules the service keeps: at most 200 items per run; two judge calls at a time (a small local judge must not be flooded); a
failing pair is reported as an error code (`scoring_failed`, `missing_contexts`, ...) and never as exception text; the judge
URL and key are never logged or echoed; Ragas telemetry is switched off.

## Set up (once)

Keep the environment outside the repo, on a drive with room. PowerShell:

```powershell
$env:UV_PROJECT_ENVIRONMENT = "C:\Users\<you>\.e2eai\ragas-venv"
uv sync --project adapters/eval/ragas --python 3.12
```

`langchain-community` is pinned below 0.4 because Ragas 0.4.3 imports a module that 0.4 removed.

## Run

```powershell
$env:UV_PROJECT_ENVIRONMENT = "C:\Users\<you>\.e2eai\ragas-venv"
uv run --project adapters/eval/ragas e2eai-adapter-ragas      # listens on 127.0.0.1:18701 (E2EAI_ADAPTER_PORT / E2EAI_ADAPTER_HOST)
```

The platform reaches it at `http://127.0.0.1:18701` (override with `lab.tools.ragas` in `e2eai.yaml`). It gives the service a
**per-run gateway key** limited to the judge and embedding models, so the master key is never shared and cost is tracked per run.

## Use

`POST /api/v1/evals/runs` with `{"dataset_id": "...", "adapter": "ragas"}` (admin). Dataset items need `question`, `answer`
and, for the context metrics, `contexts`; `expected_answer` is the reference. `ragas.local` (the deterministic offline
adapter) is still available for tests and quick checks.

## Tests

```powershell
$env:UV_PROJECT_ENVIRONMENT = "C:\Users\<you>\.e2eai\ragas-venv"
uv run --project adapters/eval/ragas pytest -q adapters/eval/ragas/tests
```
