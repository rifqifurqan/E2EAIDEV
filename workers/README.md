# E2EAIDEV worker

Background worker for document ingestion (PRD T1, FR-D3, FR-F20). It runs the **same** `ingest_version` the API uses, but
in its own process and its own Python environment, because Docling pulls PyTorch and several model files (about 1.2 GB
of packages plus models). The API stays light; the worker does the heavy parsing.

| Piece | Where |
|---|---|
| Task `e2eai.jobs.ingest.ingest_version_task` | `apps/api/src/e2eai/jobs/ingest.py` |
| Celery app (broker = Valkey database 2, results = 3) | `apps/api/src/e2eai/celery_app.py` |
| Docling conversion | `apps/api/src/e2eai/docling_runtime.py` (needs Docling, so it only imports in this environment) |
| This project: the environment + the `e2eai-worker` command | `workers/` |

## Set up (once)

Keep the environment **outside the repo, on a drive with room** (about 1.2 GB; Docling models add more under
`~/.cache/huggingface`). PowerShell:

```powershell
$env:UV_PROJECT_ENVIRONMENT = "C:\Users\<you>\.e2eai\worker-venv"
uv sync --project workers --python 3.12
```

## Run

The infrastructure must be up (`cd deploy/compose && docker compose up -d`) and `deploy/compose/.env` must exist (wizard).

```powershell
$env:UV_PROJECT_ENVIRONMENT = "C:\Users\<you>\.e2eai\worker-venv"
uv run --project workers e2eai-worker
```

* One task at a time (`--pool=solo`).
* When the worker is running, uploading a PDF, DOCX, PPTX, XLSX or image returns `parse_status: "pending"` immediately and
  the document becomes `ready` (or `failed`, with an audit entry) when the worker finishes. Text and markdown files are
  still parsed instantly inside the API.
* When no worker is running, the API falls back to parsing inline; without Docling in the API environment the version is
  recorded as `failed` with a clear reason, never lost.
* Retries: transient failures (gateway restarting, database reconnecting) are retried 3 times with backoff; after that the
  version is marked `failed`.

## Tests

```powershell
$env:UV_PROJECT_ENVIRONMENT = "C:\Users\<you>\.e2eai\worker-venv"
uv run --project workers pytest -q workers/tests
```

The Docling tests build real PDFs and images and run real conversions, so the first run downloads the models.
