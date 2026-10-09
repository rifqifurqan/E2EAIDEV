"""FR-T3/FR-T4/FR-T6 evaluator transparency and evaluator ranking."""

from types import SimpleNamespace

from e2eai.eval_lab import (
    LocalRagasAdapter,
    build_fair_judge_payloads,
    evaluate_evaluators,
)


def test_fair_judging_uses_one_judge_model_temperature_zero_and_identical_inputs():
    items = [
        {"question": "Q1", "answer": "A", "expected_answer": "A"},
        {"question": "Q2", "answer": "B", "expected_answer": "B"},
    ]
    payloads = build_fair_judge_payloads(
        items,
        frameworks=["ragas.local", "deepeval.local", "promptfoo.local"],
        judge_model="qwen3.5:4b",
    )

    assert set(payloads) == {"ragas.local", "deepeval.local", "promptfoo.local"}
    first_messages = None
    for payload in payloads.values():
        assert payload["model"] == "qwen3.5:4b"
        assert payload["temperature"] == 0
        assert payload["metric"] == "answer_correctness"
        if first_messages is None:
            first_messages = payload["messages"]
        assert payload["messages"] == first_messages


def test_metric_transparency_records_definition_and_actual_judge_prompt():
    items = [{"question": "What is revenue?", "answer": "30 percent", "expected_answer": "30 percent", "kind": "qa"}]
    adapter = LocalRagasAdapter(judge_model="qwen3.5:4b")

    import asyncio
    metrics, item_results = asyncio.run(adapter.evaluate(items))

    assert metrics["judge_model"] == "qwen3.5:4b"
    assert metrics["judge_temperature"] == 0
    assert "answer_correctness" in metrics["metric_definitions"]
    row = item_results[0]
    assert row["metric"] == "answer_correctness"
    assert row["metric_definition"] == metrics["metric_definitions"]["answer_correctness"]
    assert "Question: What is revenue?" in row["judge_prompt"]
    assert "Expected answer: 30 percent" in row["judge_prompt"]
    assert "password" not in row["judge_prompt"].lower()


def test_evaluate_evaluators_ranks_by_human_agreement_cost_latency_and_variance():
    human_labels = {"0": 1, "1": 0, "2": 1}
    runs = [
        SimpleNamespace(
            adapter="ragas.local",
            metrics={"judge_cost_usd": 0.03, "latency_ms": 120, "answer_correctness": 0.8},
            item_results=[
                {"index": 0, "score": 0.9},
                {"index": 1, "score": 0.2},
                {"index": 2, "score": 0.8},
            ],
        ),
        SimpleNamespace(
            adapter="noisy.local",
            metrics={"judge_cost_usd": 0.01, "latency_ms": 80, "answer_correctness": 0.4},
            item_results=[
                {"index": 0, "score": 0.1},
                {"index": 1, "score": 0.9},
                {"index": 2, "score": 0.2},
            ],
        ),
        # A second ragas run to prove variance across runs is tracked by adapter.
        SimpleNamespace(
            adapter="ragas.local",
            metrics={"judge_cost_usd": 0.04, "latency_ms": 150, "answer_correctness": 0.7},
            item_results=[
                {"index": 0, "score": 0.8},
                {"index": 1, "score": 0.1},
                {"index": 2, "score": 0.7},
            ],
        ),
    ]

    ranking = evaluate_evaluators(runs, human_labels=human_labels)

    assert ranking[0]["adapter"] == "ragas.local"
    assert ranking[0]["correlation"] > ranking[1]["correlation"]
    assert ranking[0]["cohens_kappa"] == 1.0
    assert ranking[0]["cost_per_100_items_usd"] > 0
    assert ranking[0]["latency_ms"] == 135.0
    assert ranking[0]["variance_across_runs"] > 0
    assert ranking[1]["adapter"] == "noisy.local"
    assert ranking[1]["cohens_kappa"] < 0
