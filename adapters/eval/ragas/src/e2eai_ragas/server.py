"""Ragas Lab adapter (PRD T6): a small HTTP service. The platform never imports Ragas; it calls this service.

    GET  /info    tool name, version, license, stage, operations, metrics and what each score means (FR-T4)
    GET  /health  liveness
    POST /run     score a batch: {run_id, operation, inputs[], config{metrics[]}, judge{base_url, model, api_key}}

Judge calls go to the platform's model gateway (an OpenAI-compatible URL), so the same judge model can be given to every
framework (FR-T3) and the cost is tracked there. The judge key and URL are used for the calls only: they are never
echoed, logged, or copied into an error message.
"""

import asyncio
import logging
import math
import os
from collections.abc import Awaitable, Callable
from typing import Any, Literal

os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")  # NFR-12: no outbound telemetry
os.environ.setdefault("DO_NOT_TRACK", "true")

from fastapi import FastAPI, HTTPException  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

log = logging.getLogger("e2eai.ragas")

MAX_ITEMS = 200
CONCURRENCY = 2  # a small local judge must not be flooded with parallel calls
JUDGE_MAX_TOKENS = 4096  # ragas defaults to 1024, which cuts a structured answer off mid-JSON on a verbose local model
METRICS = ("faithfulness", "answer_relevancy", "context_precision", "context_recall")
DEFINITIONS = {
    "faithfulness": "Share of the answer's claims that the retrieved contexts support (the judge splits the answer into "
                    "claims and checks each against the contexts). Needs: question, answer, contexts.",
    "answer_relevancy": "How well the answer addresses the question (the judge writes questions the answer would fit and "
                        "compares them with the real one using embeddings). Needs: question, answer.",
    "context_precision": "Whether the contexts that matter are ranked first among those retrieved. Needs: question, contexts, ground_truth.",
    "context_recall": "Share of the reference answer that the retrieved contexts cover. Needs: question, contexts, ground_truth.",
}
_NEEDS = {"faithfulness": ("contexts",), "answer_relevancy": (), "context_precision": ("contexts", "ground_truth"),
          "context_recall": ("contexts", "ground_truth")}

Scorer = Callable[[str, dict, dict], Awaitable[tuple[float, dict]]]


class Item(BaseModel):
    item_id: str = Field(min_length=1, max_length=120)
    question: str
    answer: str = ""
    contexts: list[str] = []
    ground_truth: str | None = None


class Judge(BaseModel):
    base_url: str
    model: str
    api_key: str = "none"
    embedding_model: str | None = None  # answer_relevancy compares embeddings
    reasoning: Literal["off", "default"] = "off"  # "off": ask thinking models not to think aloud (it eats the JSON budget)


class RunIn(BaseModel):
    run_id: str
    operation: Literal["evaluate"] = "evaluate"
    inputs: list[Item]
    config: dict[str, Any] = {}
    judge: Judge


def version() -> str:
    try:
        import importlib.metadata as md

        return md.version("ragas")
    except Exception:  # noqa: BLE001
        return "unknown"


# --- the real scorer ----------------------------------------------------------------------------------------------

_clients: dict[tuple, tuple[Any, Any]] = {}


def _judge_clients(judge: dict):
    """Ragas judge LLM + embeddings over the platform gateway. Cached per judge: building them is not free."""
    key = (judge["base_url"], judge["model"], judge.get("embedding_model"), judge.get("reasoning", "off"))
    if key not in _clients:
        from openai import AsyncOpenAI
        from ragas.embeddings import embedding_factory
        from ragas.llms import llm_factory

        client = AsyncOpenAI(base_url=judge["base_url"], api_key=judge.get("api_key") or "none", timeout=600, max_retries=1)
        options: dict[str, Any] = {"temperature": 0, "max_tokens": JUDGE_MAX_TOKENS}  # FR-T3: same settings for every framework
        if judge.get("reasoning", "off") == "off":
            options["extra_body"] = {"think": False}  # the gateway drops it for providers that do not know it
        llm = llm_factory(judge["model"], provider="openai", client=client, **options)
        emb = embedding_factory("openai", model=judge["embedding_model"], client=client) if judge.get("embedding_model") else None
        _clients[key] = (llm, emb)
    return _clients[key]


async def ragas_scorer(metric: str, item: dict, judge: dict) -> tuple[float, dict]:
    from ragas.metrics.collections import AnswerRelevancy, ContextPrecision, ContextRecall, Faithfulness

    llm, emb = _judge_clients(judge)
    if metric == "faithfulness":
        result = await Faithfulness(llm=llm).ascore(user_input=item["question"], response=item["answer"], retrieved_contexts=item["contexts"])
    elif metric == "answer_relevancy":
        if emb is None:
            raise ValueError("answer_relevancy needs judge.embedding_model")
        result = await AnswerRelevancy(llm=llm, embeddings=emb).ascore(user_input=item["question"], response=item["answer"])
    elif metric == "context_precision":
        result = await ContextPrecision(llm=llm).ascore(user_input=item["question"], reference=item["ground_truth"], retrieved_contexts=item["contexts"])
    elif metric == "context_recall":
        result = await ContextRecall(llm=llm).ascore(user_input=item["question"], retrieved_contexts=item["contexts"], reference=item["ground_truth"])
    else:  # unreachable: /run validates metric names first
        raise ValueError(metric)
    return float(result.value), {"reason": getattr(result, "reason", None)}


# --- the service ---------------------------------------------------------------------------------------------------

def create_app(scorer: Scorer | None = None) -> FastAPI:
    scorer = scorer or ragas_scorer
    app = FastAPI(title="E2EAIDEV Ragas adapter", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/info")
    def info() -> dict:
        return {"name": "ragas", "version": version(), "license": "Apache-2.0", "stage": "test", "operations": ["evaluate"],
                "metrics": list(METRICS), "definitions": DEFINITIONS}

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "version": version()}

    @app.post("/run")
    async def run(body: RunIn) -> dict:
        metrics = body.config.get("metrics") or ["faithfulness"]
        unknown = [m for m in metrics if m not in METRICS]
        if unknown:
            raise HTTPException(422, detail={"error": "unknown_metric", "allowed": list(METRICS)})
        if not body.inputs:
            raise HTTPException(422, detail={"error": "no_inputs"})
        if len(body.inputs) > MAX_ITEMS:
            raise HTTPException(413, detail={"error": "too_many_items", "max": MAX_ITEMS})

        judge = body.judge.model_dump()
        gate = asyncio.Semaphore(CONCURRENCY)

        async def score_one(it: Item, metric: str):
            data = it.model_dump()
            for needed in _NEEDS[metric]:
                if not data.get(needed):
                    return None, {"item_id": it.item_id, "metric": metric, "error": f"missing_{needed}"}
            async with gate:
                try:
                    score, details = await scorer(metric, data, judge)
                except Exception as exc:  # noqa: BLE001 - only the exception TYPE is logged: messages can carry the judge URL or key
                    log.warning("scoring failed: %s %s %s", it.item_id, metric, type(exc).__name__)
                    return None, {"item_id": it.item_id, "metric": metric, "error": "scoring_failed"}
            if not isinstance(score, (int, float)) or math.isnan(score) or not 0.0 <= score <= 1.0:
                return None, {"item_id": it.item_id, "metric": metric, "error": "score_out_of_range"}
            return {"item_id": it.item_id, "metric": metric, "score": float(score), "details": details or {}, "framework": "ragas"}, None

        outcomes = await asyncio.gather(*(score_one(it, m) for it in body.inputs for m in metrics))
        return {"run_id": body.run_id, "tool": "ragas", "version": version(),
                "rows": [row for row, _ in outcomes if row], "errors": [err for _, err in outcomes if err]}

    return app


def main() -> None:
    import uvicorn

    uvicorn.run(create_app(), host=os.environ.get("E2EAI_ADAPTER_HOST", "127.0.0.1"),
                port=int(os.environ.get("E2EAI_ADAPTER_PORT", "18701")), log_level="info")


if __name__ == "__main__":
    main()
