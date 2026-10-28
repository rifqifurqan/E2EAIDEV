"""Real Ragas, reached through its Lab adapter service (PRD T6, FR-T2, FR-T3).

The platform never imports Ragas: it POSTs the dataset to the adapter service (`adapters/eval/ragas`) and normalizes the
reply to the same `(metrics, item_results)` shape every other framework returns, so runs can be compared (FR-T12).
The judge is a model on the platform gateway. Each run gets its own short-lived gateway key, so cost is tracked per run
(FR-L4) and the tool never sees the master key.
"""

import logging
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

import httpx

from .core.errors import AppError

log = logging.getLogger("e2eai.ragas")
DEFAULT_METRICS = ("faithfulness", "answer_relevancy")  # neither needs a reference answer
MAX_REASON_CHARS = 500


@dataclass
class RagasHttpAdapter:
    base_url: str
    judge_base_url: str          # OpenAI-compatible gateway URL, ending in /v1
    judge_model: str
    judge_api_key: str           # the per-run key from create_judge_key(), never the master key
    embedding_model: str | None = None
    metrics: tuple[str, ...] = DEFAULT_METRICS
    name: str = "ragas"
    timeout: float = 3600.0      # a small local judge is slow; the service bounds the batch size itself
    transport: httpx.AsyncBaseTransport | None = None  # tests

    async def evaluate(self, items: Sequence[dict]) -> tuple[dict, list[dict]]:
        run_id = uuid.uuid4().hex
        body = {
            "run_id": run_id, "operation": "evaluate", "config": {"metrics": list(self.metrics)},
            "inputs": [{"item_id": str(i), "question": str(it.get("question") or ""), "answer": str(it.get("answer") or ""),
                        "contexts": [str(c) for c in (it.get("contexts") or [])], "ground_truth": it.get("expected_answer")}
                       for i, it in enumerate(items)],
            "judge": {"base_url": self.judge_base_url, "model": self.judge_model, "api_key": self.judge_api_key,
                      "embedding_model": self.embedding_model},
        }
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout, transport=self.transport) as client:
                info = (await client.get("/info")).json()
                reply = await client.post("/run", json=body)
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("ragas service unreachable: %s", type(exc).__name__)  # never the message: it can carry the URL or key
            raise AppError(503, "Ragas service unavailable", "Start the Ragas adapter (see adapters/eval/ragas/README.md).") from exc
        if reply.status_code >= 400:
            log.warning("ragas service rejected the run: HTTP %s", reply.status_code)
            raise AppError(502, "Ragas run rejected", f"The Ragas service answered HTTP {reply.status_code}.")
        data = reply.json()

        results: list[dict] = []
        scores: dict[str, list[float]] = {}
        definitions = info.get("definitions", {})
        for row in data.get("rows", []):
            index = int(row["item_id"])
            scores.setdefault(row["metric"], []).append(float(row["score"]))
            details = dict(row.get("details") or {})
            if isinstance(details.get("reason"), str):
                details["reason"] = details["reason"][:MAX_REASON_CHARS]
            results.append({"index": index, "item_id": row["item_id"], "metric": row["metric"], "score": float(row["score"]),
                            "kind": items[index].get("kind", "qa"), "metric_definition": definitions.get(row["metric"], ""),
                            "judge_model": self.judge_model, "judge_temperature": 0, "details": details})
        errors = [{"index": int(e["item_id"]), "metric": e["metric"], "error": e["error"]} for e in data.get("errors", [])]
        metrics: dict = {m: round(sum(v) / len(v), 4) for m, v in scores.items()}
        metrics |= {"items": len(items), "scored": len(results), "failed": len(errors), "errors": errors,
                    "judge_model": self.judge_model, "judge_temperature": 0, "metric_definitions": definitions,
                    "tool": "ragas", "tool_version": data.get("version") or info.get("version", "")}
        return metrics, results


async def create_judge_key(litellm_url: str, master_key: str, *, run_id: str, models: Sequence[str],
                           max_budget_usd: float = 1.0, duration: str = "2h",
                           transport: httpx.AsyncBaseTransport | None = None) -> str:
    """A short-lived gateway key limited to the judge (and embedding) model. No fallback to the master key."""
    alias = "lab-" + (re.sub(r"[^a-z0-9]+", "", run_id.lower())[:16] or "run")
    try:
        async with httpx.AsyncClient(base_url=litellm_url, timeout=15.0, transport=transport) as client:
            reply = await client.post("/key/generate", headers={"Authorization": f"Bearer {master_key}"},
                                      json={"key_alias": alias, "models": list(models), "duration": duration, "max_budget": max_budget_usd})
        reply.raise_for_status()
        return reply.json()["key"]
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        log.warning("judge key generation failed: %s", type(exc).__name__)
        raise AppError(503, "Could not create a judge key", "The model gateway refused to issue a run key; the evaluation was not started.") from exc


async def build_ragas_adapter(settings, *, run_id: str, metrics: Sequence[str] | None = None,
                              gateway_transport: httpx.AsyncBaseTransport | None = None,
                              service_transport: httpx.AsyncBaseTransport | None = None) -> RagasHttpAdapter:
    """The adapter for one run: judge and embedding model from e2eai.yaml, plus a per-run gateway key."""
    if not settings.lab_judge_model:
        raise AppError(503, "No judge model configured", "Choose a chat model in the install wizard, or set lab.judge_model in e2eai.yaml.")
    models = [settings.lab_judge_model] + ([settings.lab_embedding_model] if settings.lab_embedding_model else [])
    key = await create_judge_key(settings.litellm_url, settings.litellm_key, run_id=run_id, models=models, transport=gateway_transport)
    return RagasHttpAdapter(base_url=settings.lab_ragas_url, judge_base_url=settings.litellm_url.rstrip("/") + "/v1",
                            judge_model=settings.lab_judge_model, judge_api_key=key,
                            embedding_model=settings.lab_embedding_model or None,
                            metrics=tuple(metrics) if metrics else DEFAULT_METRICS, transport=service_transport)
