"""FR-O3 online evaluation on sampled production traffic.

Deterministic/offline: a sticky hash sampler picks a share of traces, a pluggable scorer rates each
sampled trace, and only aggregates/labels are stored (never prompts, answers, or user ids).
"""

import asyncio
import subprocess

import pytest


def _migrate():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)


def _traces(n=2000):
    return [
        {"trace_id": f"t{i}", "bot_version": "v2" if i % 2 else "v1", "answered": i % 10 != 0,
         "has_citation": i % 4 != 0, "feedback": "down" if i % 25 == 0 else None,
         "question": "secret question", "answer": "secret answer"}
        for i in range(n)
    ]


def test_sampler_is_sticky_and_matches_rate():
    from e2eai.online_eval import should_sample

    assert should_sample("t1", rate=0.0, salt="s") is False
    assert should_sample("t1", rate=1.0, salt="s") is True
    assert should_sample("t42", rate=0.3, salt="s") == should_sample("t42", rate=0.3, salt="s")
    hits = sum(should_sample(f"t{i}", rate=0.1, salt="s") for i in range(5000))
    assert 380 < hits < 620
    with pytest.raises(ValueError):
        should_sample("t", rate=1.5, salt="s")


def test_heuristic_scorer_uses_only_safe_signals():
    from e2eai.online_eval import heuristic_score

    good = heuristic_score({"answered": True, "has_citation": True, "feedback": None})
    assert good == {"score": 1.0, "flags": []}
    weak = heuristic_score({"answered": True, "has_citation": False, "feedback": "down"})
    assert weak["score"] == 0.2 and weak["flags"] == ["no_citation", "negative_feedback"]
    unanswered = heuristic_score({"answered": False, "has_citation": False, "feedback": None})
    assert unanswered["score"] == 0.0 and "unanswered" in unanswered["flags"]


def test_run_online_eval_aggregates_by_bot_version_and_flags_low_quality():
    from e2eai.online_eval import run_online_eval

    result = run_online_eval(_traces(), rate=0.25, salt="o3", min_quality=0.9)
    assert 400 < result["sampled"] < 600 and result["total"] == 2000
    assert set(result["by_bot_version"]) == {"v1", "v2"}
    for stats in result["by_bot_version"].values():
        assert 0.0 <= stats["mean_score"] <= 1.0 and stats["n"] > 0
    assert result["alert"] is True and result["alert_reason"] == "mean_quality_below_threshold"
    assert result["flag_counts"]["unanswered"] > 0
    assert "trace_ids_flagged" in result and all(isinstance(t, str) for t in result["trace_ids_flagged"])
    assert "secret" not in str(result)

    quiet = run_online_eval(_traces(100), rate=0.0, salt="o3", min_quality=0.5)
    assert quiet["sampled"] == 0 and quiet["alert"] is False


def test_stored_run_has_no_content_and_routes_are_wired():
    async def run():
        from e2eai.db import sessions
        from e2eai.online_eval import evaluate_online_traffic

        async with sessions()() as session:
            row = await evaluate_online_traffic(
                session, name="online-eval", traces=_traces(400), rate=0.5, salt="o3", min_quality=0.5, created_by="test"
            )
            assert row.adapter == "online-eval.local"
            assert row.metrics["sampled"] > 0
            stored = str(row.metrics) + str(row.item_results)
            assert "secret question" not in stored and "secret answer" not in stored

    _migrate()
    asyncio.run(run())

    from e2eai.main import app

    assert "post" in app.openapi()["paths"]["/api/v1/evals/online"]
