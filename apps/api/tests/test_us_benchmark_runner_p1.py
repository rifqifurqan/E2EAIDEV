"""FR-T11 Benchmark runner: model x prompt x dataset leaderboard."""

import asyncio

from sqlalchemy import delete, select

from e2eai.benchmark import build_benchmark_leaderboard, run_benchmark, summarize_combination
from e2eai.db import EvalDataset, EvalRun, sessions


def test_summarize_combination_computes_quality_latency_ttft_tokens_cost():
    combo = {
        "model": "qwen3.5:4b",
        "prompt": "concise-v1",
        "dataset": "rag-smoke",
        "samples": [
            {"quality": 1.0, "latency_ms": 100, "ttft_ms": 10, "output_tokens": 40, "cost_usd": 0.001},
            {"quality": 0.0, "latency_ms": 200, "ttft_ms": 20, "output_tokens": 40, "cost_usd": 0.001},
            {"quality": 1.0, "latency_ms": 300, "ttft_ms": 30, "output_tokens": 40, "cost_usd": 0.001},
        ],
    }
    row = summarize_combination(combo)

    assert row["model"] == "qwen3.5:4b"
    assert row["prompt"] == "concise-v1"
    assert row["dataset"] == "rag-smoke"
    assert row["samples"] == 3
    assert row["quality"] == 0.6667
    # linear-interpolation percentiles over [100,200,300] and [10,20,30]
    assert row["latency_p50_ms"] == 200
    assert row["latency_p95_ms"] == 290
    assert row["ttft_p50_ms"] == 20
    assert row["ttft_p95_ms"] == 29
    # mean of 40/0.1, 40/0.2, 40/0.3 tokens/s
    assert row["tokens_per_s"] == 244.4444
    assert row["cost_usd"] == 0.003


def test_build_leaderboard_sorts_by_quality_then_latency():
    combos = [
        {"model": "m-slow-good", "prompt": "p1", "dataset": "d", "samples": [
            {"quality": 1.0, "latency_ms": 500, "ttft_ms": 50, "output_tokens": 10, "cost_usd": 0.01},
        ]},
        {"model": "m-fast-good", "prompt": "p1", "dataset": "d", "samples": [
            {"quality": 1.0, "latency_ms": 100, "ttft_ms": 10, "output_tokens": 10, "cost_usd": 0.01},
        ]},
        {"model": "m-bad", "prompt": "p1", "dataset": "d", "samples": [
            {"quality": 0.2, "latency_ms": 50, "ttft_ms": 5, "output_tokens": 10, "cost_usd": 0.01},
        ]},
    ]
    board = build_benchmark_leaderboard(combos)

    # highest quality first; ties broken by lower p50 latency
    assert [r["model"] for r in board] == ["m-fast-good", "m-slow-good", "m-bad"]


def test_run_benchmark_stores_eval_run_with_safe_leaderboard():
    async def run():
        async with sessions()() as session:
            await session.execute(delete(EvalRun))
            await session.execute(delete(EvalDataset))
            await session.commit()

            run = await run_benchmark(
                session,
                name="nightly-bench",
                created_by="test",
                combinations=[
                    {"model": "qwen3.5:4b", "prompt": "concise-v1", "dataset": "rag-smoke", "samples": [
                        {"quality": 1.0, "latency_ms": 120, "ttft_ms": 12, "output_tokens": 30, "cost_usd": 0.002},
                        {"quality": 0.8, "latency_ms": 140, "ttft_ms": 14, "output_tokens": 30, "cost_usd": 0.002},
                        # answer text must never be persisted
                        {"quality": 0.9, "latency_ms": 130, "ttft_ms": 13, "output_tokens": 30, "cost_usd": 0.002,
                         "answer": "secret revenue-share is 30 percent"},
                    ]},
                    {"model": "llama3.2:1b", "prompt": "concise-v1", "dataset": "rag-smoke", "samples": [
                        {"quality": 0.5, "latency_ms": 60, "ttft_ms": 6, "output_tokens": 30, "cost_usd": 0.001},
                    ]},
                ],
            )

            assert run.adapter == "benchmark.local"
            assert run.status == "completed"
            assert run.metrics["combinations"] == 2
            assert run.metrics["models"] == ["llama3.2:1b", "qwen3.5:4b"]
            assert run.metrics["datasets"] == ["rag-smoke"]
            assert run.metrics["best"]["model"] == "qwen3.5:4b"  # higher quality wins
            assert run.metrics["total_cost_usd"] == 0.007

            # item_results is the leaderboard: safe fields only, no raw answers persisted
            assert len(run.item_results) == 2
            stored = (await session.scalars(select(EvalRun).where(EvalRun.adapter == "benchmark.local"))).all()
            assert len(stored) == 1
            serialized = str(stored[0].item_results) + str(stored[0].metrics)
            assert "30 percent" not in serialized
            assert "answer" not in serialized

    asyncio.run(run())
