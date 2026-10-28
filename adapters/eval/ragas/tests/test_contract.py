"""PRD T6: every Lab tool answers /info, /health and /run in the same shape. Tested with a fake scorer (no LLM, no network)."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from e2eai_ragas.server import MAX_ITEMS, METRICS, create_app

JUDGE = {"base_url": "http://gateway.invalid/v1", "model": "judge-model", "api_key": "sk-SECRET-JUDGE-KEY-123456"}


def item(item_id="q1", **over):
    base = {"item_id": item_id, "question": "What is the revenue share?", "answer": "70/30.", "contexts": ["The split is 70/30."],
            "ground_truth": "70 percent platform, 30 percent partner"}
    return base | over


async def good_scorer(metric, it, judge):
    return 0.8, {"note": f"scored {metric}"}


def client(scorer=good_scorer):
    return TestClient(create_app(scorer=scorer))


def test_info_describes_the_tool_its_license_and_every_metric():
    body = client().get("/info").json()
    assert body["name"] == "ragas" and body["stage"] == "test" and body["license"] == "Apache-2.0"
    assert body["operations"] == ["evaluate"] and isinstance(body["version"], str) and body["version"]
    assert set(body["metrics"]) == set(METRICS)
    assert all(body["definitions"][m] for m in METRICS)  # FR-T4: what each score means, in words


def test_health_is_a_cheap_liveness_probe():
    body = client().get("/health").json()
    assert body["status"] == "ok" and body["version"]


def test_run_returns_one_normalized_row_per_item_and_metric():
    r = client().post("/run", json={"run_id": "r1", "inputs": [item("a"), item("b")], "config": {"metrics": ["faithfulness", "answer_relevancy"]}, "judge": JUDGE})
    assert r.status_code == 200
    body = r.json()
    assert body["run_id"] == "r1" and body["errors"] == []
    assert sorted((row["item_id"], row["metric"]) for row in body["rows"]) == [
        ("a", "answer_relevancy"), ("a", "faithfulness"), ("b", "answer_relevancy"), ("b", "faithfulness")]
    assert all(0.0 <= row["score"] <= 1.0 and row["framework"] == "ragas" for row in body["rows"])


def test_the_judge_key_is_never_echoed():
    r = client().post("/run", json={"run_id": "r2", "inputs": [item()], "config": {"metrics": ["faithfulness"]}, "judge": JUDGE})
    assert "SECRET-JUDGE-KEY" not in r.text and "gateway.invalid" not in r.text


def test_an_unknown_metric_is_rejected_with_the_allowed_names():
    r = client().post("/run", json={"run_id": "r3", "inputs": [item()], "config": {"metrics": ["vibes"]}, "judge": JUDGE})
    assert r.status_code == 422 and "faithfulness" in r.text


def test_a_failing_pair_is_reported_but_the_others_are_still_scored():
    async def flaky(metric, it, judge):
        if it["item_id"] == "bad":
            raise RuntimeError("judge said http://gateway.invalid/v1 key sk-SECRET-JUDGE-KEY-123456")
        return 0.5, {}

    r = client(flaky).post("/run", json={"run_id": "r4", "inputs": [item("ok"), item("bad")], "config": {"metrics": ["faithfulness"]}, "judge": JUDGE})
    body = r.json()
    assert [row["item_id"] for row in body["rows"]] == ["ok"]
    assert body["errors"] == [{"item_id": "bad", "metric": "faithfulness", "error": "scoring_failed"}]  # a code, never the exception text
    assert "SECRET" not in r.text and "gateway.invalid" not in r.text


def test_an_item_missing_what_a_metric_needs_is_an_error_not_a_crash():
    r = client().post("/run", json={"run_id": "r5", "inputs": [item("x", contexts=[])], "config": {"metrics": ["faithfulness"]}, "judge": JUDGE})
    assert r.json()["errors"] == [{"item_id": "x", "metric": "faithfulness", "error": "missing_contexts"}]


def test_a_metric_that_needs_a_reference_answer_says_so():
    r = client().post("/run", json={"run_id": "r6", "inputs": [item("y", ground_truth=None)], "config": {"metrics": ["context_recall"]}, "judge": JUDGE})
    assert r.json()["errors"] == [{"item_id": "y", "metric": "context_recall", "error": "missing_ground_truth"}]


def test_too_many_items_are_refused_before_any_judge_call():
    calls = []

    async def counting(metric, it, judge):
        calls.append(1)
        return 1.0, {}

    r = client(counting).post("/run", json={"run_id": "r7", "inputs": [item(str(i)) for i in range(MAX_ITEMS + 1)], "config": {"metrics": ["faithfulness"]}, "judge": JUDGE})
    assert r.status_code == 413 and calls == []


def test_a_score_outside_zero_to_one_is_not_passed_through():
    async def wild(metric, it, judge):
        return 7.5, {}

    r = client(wild).post("/run", json={"run_id": "r8", "inputs": [item()], "config": {"metrics": ["faithfulness"]}, "judge": JUDGE})
    assert r.json()["rows"] == [] and r.json()["errors"][0]["error"] == "score_out_of_range"


def test_scoring_runs_with_bounded_concurrency():
    live = {"now": 0, "peak": 0}

    async def slow(metric, it, judge):
        live["now"] += 1
        live["peak"] = max(live["peak"], live["now"])
        await asyncio.sleep(0.02)
        live["now"] -= 1
        return 0.5, {}

    client(slow).post("/run", json={"run_id": "r9", "inputs": [item(str(i)) for i in range(12)], "config": {"metrics": ["faithfulness"]}, "judge": JUDGE})
    assert 1 <= live["peak"] <= 2, "a small local judge must not be flooded with parallel calls"


# --- the judge is configured to be deterministic and to leave room for structured output ---------------------------

def test_the_judge_llm_is_deterministic_has_room_for_json_and_does_not_think_aloud(monkeypatch):
    import ragas.llms as ragas_llms

    from e2eai_ragas import server

    captured = {}
    monkeypatch.setattr(ragas_llms, "llm_factory", lambda model, **kw: captured.update(model=model, **kw) or object())
    monkeypatch.setattr(server, "_clients", {})
    server._judge_clients({"base_url": "http://gateway.invalid/v1", "model": "judge-model", "api_key": "k"})
    assert captured["temperature"] == 0                      # FR-T3: the same judge settings for every framework
    assert captured["max_tokens"] >= 4096                    # ragas defaults to 1024: a 'thinking' local model gets cut off mid-JSON
    assert captured["extra_body"] == {"think": False}        # thinking tokens would eat that budget


def test_reasoning_can_be_left_to_the_model_when_the_caller_asks():
    import ragas.llms as ragas_llms

    from e2eai_ragas import server

    captured = {}
    ragas_llms_factory = lambda model, **kw: captured.update(kw) or object()  # noqa: E731
    import pytest as _pytest
    with _pytest.MonkeyPatch.context() as mp:
        mp.setattr(ragas_llms, "llm_factory", ragas_llms_factory)
        mp.setattr(server, "_clients", {})
        server._judge_clients({"base_url": "http://gateway.invalid/v1", "model": "judge-model", "api_key": "k", "reasoning": "default"})
    assert "extra_body" not in captured
