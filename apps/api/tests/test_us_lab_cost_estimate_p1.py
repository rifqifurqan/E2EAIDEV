"""FR-L4 Lab cost/time estimates before eval runs."""

from e2eai.eval_lab import estimate_eval_run_cost


def test_estimate_eval_run_cost_counts_judge_tokens_and_gpu_minutes():
    estimate = estimate_eval_run_cost(
        [
            {"question": "What is revenue?", "answer": "30 percent", "expected_answer": "30 percent"},
            {"question": "What is leave?", "answer": "12 days", "expected_answer": "12 days"},
        ],
        judge_price_per_1k_tokens_usd=0.002,
        gpu_price_per_minute_usd=0.05,
        expected_gpu_minutes=2.0,
        budget_threshold_usd=0.50,
    )

    assert estimate["items"] == 2
    assert estimate["judge_tokens"] > 0
    assert estimate["judge_cost_usd"] > 0
    assert estimate["gpu_minutes"] == 2.0
    assert estimate["gpu_cost_usd"] == 0.1
    assert estimate["total_cost_usd"] == round(estimate["judge_cost_usd"] + 0.1, 4)
    assert estimate["requires_confirmation"] is False


def test_estimate_eval_run_cost_flags_budget_threshold():
    estimate = estimate_eval_run_cost(
        [{"question": "Q", "answer": "A", "expected_answer": "A"}],
        judge_price_per_1k_tokens_usd=1.0,
        gpu_price_per_minute_usd=2.0,
        expected_gpu_minutes=1.0,
        budget_threshold_usd=0.01,
    )

    assert estimate["total_cost_usd"] > 0.01
    assert estimate["requires_confirmation"] is True
    assert "budget" in estimate["confirmation_reason"].lower()
