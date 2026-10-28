"""FR-T2 / FR-T3 / PRD T6: real Ragas is reached through its Lab adapter service. The platform never imports Ragas.
No network: the adapter service and the model gateway are faked with httpx.MockTransport."""

import asyncio
import json

import httpx
import pytest

from e2eai.core.errors import AppError
from e2eai.ragas_http_adapter import RagasHttpAdapter, create_judge_key

ITEMS = [
    {"question": "What is the revenue share?", "answer": "The partner gets 30 percent.", "expected_answer": "30 percent",
     "contexts": ["The partner receives 30 percent of revenue."], "kind": "qa"},
    {"question": "How long is the term?", "answer": "Two years.", "expected_answer": "2 years", "kind": "qa"},
]
INFO = {"name": "ragas", "version": "0.4.3", "definitions": {"faithfulness": "claims supported by contexts", "answer_relevancy": "answers the question"}}


def adapter(handler, **over) -> RagasHttpAdapter:
    return RagasHttpAdapter(base_url="http://ragas.test", judge_base_url="http://gateway.test/v1", judge_model="qwen-judge",
                            judge_api_key="sk-run-key-000111", embedding_model="embed-model",
                            transport=httpx.MockTransport(handler), **over)


def service(rows, errors=()):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/info":
            return httpx.Response(200, json=INFO)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"run_id": seen["body"]["run_id"], "tool": "ragas", "version": "0.4.3", "rows": rows, "errors": list(errors)})

    return handler, seen


def run(adp, items=ITEMS):
    return asyncio.run(adp.evaluate(items))


def test_dataset_items_become_service_inputs_with_the_judge_and_metrics():
    handler, seen = service([])
    run(adapter(handler, metrics=("faithfulness",)))
    body = seen["body"]
    assert body["operation"] == "evaluate" and body["config"] == {"metrics": ["faithfulness"]} and body["run_id"]
    assert body["inputs"][0] == {"item_id": "0", "question": "What is the revenue share?", "answer": "The partner gets 30 percent.",
                                 "contexts": ["The partner receives 30 percent of revenue."], "ground_truth": "30 percent"}
    assert body["inputs"][1]["contexts"] == [] and body["inputs"][1]["ground_truth"] == "2 years"
    assert body["judge"] == {"base_url": "http://gateway.test/v1", "model": "qwen-judge", "api_key": "sk-run-key-000111", "embedding_model": "embed-model"}


def test_the_response_is_normalized_like_every_other_framework():
    rows = [{"item_id": "0", "metric": "faithfulness", "score": 1.0, "details": {"reason": "supported"}, "framework": "ragas"},
            {"item_id": "1", "metric": "faithfulness", "score": 0.5, "details": {}, "framework": "ragas"}]
    handler, _ = service(rows)
    metrics, results = run(adapter(handler, metrics=("faithfulness",)))
    assert metrics["faithfulness"] == 0.75 and metrics["items"] == 2 and metrics["scored"] == 2 and metrics["failed"] == 0
    assert metrics["judge_model"] == "qwen-judge" and metrics["judge_temperature"] == 0
    assert metrics["tool"] == "ragas" and metrics["tool_version"] == "0.4.3"
    assert metrics["metric_definitions"]["faithfulness"] == "claims supported by contexts"  # the real definition, shown next to the score (FR-T4)
    assert [(r["index"], r["metric"], r["score"]) for r in results] == [(0, "faithfulness", 1.0), (1, "faithfulness", 0.5)]
    assert results[0]["judge_model"] == "qwen-judge" and results[0]["kind"] == "qa"


def test_failed_pairs_are_counted_and_do_not_distort_the_averages():
    rows = [{"item_id": "0", "metric": "faithfulness", "score": 0.9, "details": {}, "framework": "ragas"}]
    errors = [{"item_id": "1", "metric": "faithfulness", "error": "scoring_failed"}]
    handler, _ = service(rows, errors)
    metrics, results = run(adapter(handler, metrics=("faithfulness",)))
    assert metrics["faithfulness"] == 0.9 and metrics["scored"] == 1 and metrics["failed"] == 1
    assert metrics["errors"] == [{"index": 1, "metric": "faithfulness", "error": "scoring_failed"}] and len(results) == 1


def test_a_long_judge_reason_is_trimmed():
    rows = [{"item_id": "0", "metric": "faithfulness", "score": 1.0, "details": {"reason": "x" * 5000}, "framework": "ragas"}]
    handler, _ = service(rows)
    _, results = run(adapter(handler, metrics=("faithfulness",)), ITEMS[:1])
    assert len(results[0]["details"]["reason"]) <= 500


def test_an_unreachable_service_is_a_clear_503_without_internal_names():
    def down(request):
        raise httpx.ConnectError("refused on http://ragas.test with key sk-run-key-000111")

    with pytest.raises(AppError) as err:
        run(adapter(down))
    assert err.value.status == 503 and "sk-run-key" not in err.value.detail and "ragas.test" not in err.value.detail


def test_a_rejected_run_surfaces_a_502_that_never_echoes_the_service_reply():
    def rejects(request):
        if request.url.path == "/info":
            return httpx.Response(200, json=INFO)
        return httpx.Response(422, json={"detail": {"error": "unknown_metric", "echo": "sk-run-key-000111"}})

    with pytest.raises(AppError) as err:
        run(adapter(rejects))
    assert err.value.status == 502 and "sk-run-key" not in (err.value.detail + err.value.title)


# --- the per-run judge key (cost is tracked by the gateway, FR-L4); never the master key -----------------------

def gateway(status=200, key="sk-generated-0001"):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(status, json={"key": key})

    return handler, seen


def test_a_judge_key_is_generated_per_run_with_a_valid_alias_and_only_the_needed_models():
    handler, seen = gateway()
    key = asyncio.run(create_judge_key("http://gateway.test", "sk-MASTER", run_id="01A181DF-A1B6-7C97",
                                       models=["qwen-judge", "embed-model"], transport=httpx.MockTransport(handler)))
    assert key == "sk-generated-0001" and seen["auth"] == "Bearer sk-MASTER"
    body = seen["body"]
    assert body["models"] == ["qwen-judge", "embed-model"] and body["duration"] and body["max_budget"] > 0
    import re
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", body["key_alias"])  # the gateway's alias rule


def test_when_a_judge_key_cannot_be_made_the_run_stops_instead_of_using_the_master_key():
    handler, _ = gateway(status=500)
    with pytest.raises(AppError) as err:
        asyncio.run(create_judge_key("http://gateway.test", "sk-MASTER", run_id="abc", models=["m"], transport=httpx.MockTransport(handler)))
    assert err.value.status == 503 and "MASTER" not in err.value.detail


# --- wiring from e2eai.yaml and the gateway -------------------------------------------------------------------

from types import SimpleNamespace  # noqa: E402

from e2eai.core.config import lab_settings  # noqa: E402
from e2eai.ragas_http_adapter import build_ragas_adapter  # noqa: E402


def test_lab_settings_default_to_the_first_chat_and_embedding_model_and_the_standard_port():
    cfg = {"models": {"chat": ["qwen3.5:4b", "qwen3:8b"], "embedding": ["bge-m3"]}}
    assert lab_settings(cfg) == {"ragas_url": "http://127.0.0.1:18701", "judge_model": "qwen3.5:4b", "embedding_model": "bge-m3"}


def test_lab_settings_can_be_overridden_in_the_lab_section():
    cfg = {"models": {"chat": ["a"], "embedding": ["e"]},
           "lab": {"judge_model": "b", "embedding_model": "f", "tools": {"ragas": "http://10.0.0.5:9000/"}}}
    assert lab_settings(cfg) == {"ragas_url": "http://10.0.0.5:9000", "judge_model": "b", "embedding_model": "f"}


def test_an_install_without_models_has_no_judge():
    assert lab_settings({})["judge_model"] == ""


def test_build_ragas_adapter_asks_the_gateway_for_a_run_key_limited_to_the_judge_and_embedding_models():
    handler, seen = gateway(key="sk-run-xyz-0002")
    settings = SimpleNamespace(litellm_url="http://gateway.test", litellm_key="sk-MASTER", lab_ragas_url="http://ragas.test",
                               lab_judge_model="qwen-judge", lab_embedding_model="embed-model")
    adp = asyncio.run(build_ragas_adapter(settings, run_id="r-1", gateway_transport=httpx.MockTransport(handler)))
    assert adp.judge_api_key == "sk-run-xyz-0002" and adp.judge_api_key != "sk-MASTER"
    assert adp.judge_base_url == "http://gateway.test/v1" and adp.base_url == "http://ragas.test"
    assert seen["body"]["models"] == ["qwen-judge", "embed-model"]


def test_build_ragas_adapter_refuses_to_start_without_a_judge_model():
    settings = SimpleNamespace(litellm_url="http://g", litellm_key="k", lab_ragas_url="http://r", lab_judge_model="", lab_embedding_model="")
    with pytest.raises(AppError) as err:
        asyncio.run(build_ragas_adapter(settings, run_id="r-2"))
    assert err.value.status == 503
