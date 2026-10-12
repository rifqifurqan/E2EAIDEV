"""FR-B5 agent workflows (multi-step tool chains) with agent-trajectory evaluation.

Deterministic/offline: a workflow is a validated dependency-ordered step list run through an injected tool
runner (bounded steps, allow-listed tools only); the recorded trajectory is scored against an expected
trajectory (tool selection, order, argument match, step efficiency, final-answer check). Trajectories
store tool names, argument keys, and status only: never argument values or tool outputs.
"""

import asyncio

import pytest


def _run(coro):
    return asyncio.run(coro)


def test_workflow_validation():
    from e2eai.agent_workflow import validate_workflow

    ok = validate_workflow({"steps": [{"id": "a", "tool": "lookup"}, {"id": "b", "tool": "calc", "depends_on": ["a"]}]})
    assert [s["id"] for s in ok["steps"]] == ["a", "b"]
    for bad in (
        {"steps": []},
        {"steps": [{"id": "a", "tool": "x"}, {"id": "a", "tool": "y"}]},  # duplicate id
        {"steps": [{"id": "a", "tool": "x", "depends_on": ["zz"]}]},  # unknown dependency
        {"steps": [{"id": "a", "tool": "x", "depends_on": ["b"]}, {"id": "b", "tool": "y", "depends_on": ["a"]}]},  # cycle
        {"steps": [{"id": f"s{i}", "tool": "x"} for i in range(26)]},  # too many steps
        {"steps": [{"id": "a", "tool": ""}]},
    ):
        with pytest.raises(ValueError):
            validate_workflow(bad)


def test_run_workflow_in_dependency_order_with_safe_trajectory():
    from e2eai.agent_workflow import run_workflow

    calls = []

    async def runner(tool, args):
        calls.append(tool)
        return {"ok": True, "output": "SECRET-OUTPUT-123"}

    wf = {"steps": [
        {"id": "b", "tool": "calc", "args": {"x": 1}, "depends_on": ["a"]},
        {"id": "a", "tool": "lookup", "args": {"q": "private question text"}},
    ]}
    traj = _run(run_workflow(wf, runner, allowed_tools={"lookup", "calc"}))
    assert calls == ["lookup", "calc"]
    assert [s["tool"] for s in traj["steps"]] == ["lookup", "calc"]
    assert traj["steps"][0]["arg_keys"] == ["q"] and traj["status"] == "completed"
    blob = str(traj)
    assert "SECRET-OUTPUT-123" not in blob and "private question text" not in blob


def test_disallowed_tool_and_failure_stop_the_run():
    from e2eai.agent_workflow import run_workflow

    async def runner(tool, args):
        if tool == "boom":
            raise RuntimeError("secret detail")
        return {"ok": True}

    wf = {"steps": [{"id": "a", "tool": "write_db"}, {"id": "b", "tool": "lookup", "depends_on": ["a"]}]}
    traj = _run(run_workflow(wf, runner, allowed_tools={"lookup"}))
    assert traj["status"] == "blocked" and traj["steps"][0]["status"] == "blocked" and len(traj["steps"]) == 1

    wf2 = {"steps": [{"id": "a", "tool": "boom"}, {"id": "b", "tool": "lookup", "depends_on": ["a"]}]}
    traj2 = _run(run_workflow(wf2, runner, allowed_tools={"boom", "lookup"}))
    assert traj2["status"] == "failed" and traj2["steps"][0]["error_code"] == "tool_error"
    assert "secret detail" not in str(traj2) and len(traj2["steps"]) == 1


def test_score_perfect_trajectory():
    from e2eai.agent_workflow import score_trajectory

    actual = [{"tool": "lookup", "arg_keys": ["q"], "status": "ok"}, {"tool": "calc", "arg_keys": ["x"], "status": "ok"}]
    expected = [{"tool": "lookup", "arg_keys": ["q"]}, {"tool": "calc", "arg_keys": ["x"]}]
    s = score_trajectory(actual, expected)
    assert s["tool_selection"] == 1.0 and s["order"] == 1.0 and s["arguments"] == 1.0 and s["efficiency"] == 1.0
    assert s["score"] == 1.0 and s["passed"] is True and s["extra_steps"] == 0 and s["missing_tools"] == []


def test_score_penalises_wrong_order_extra_and_missing_steps():
    from e2eai.agent_workflow import score_trajectory

    expected = [{"tool": "lookup", "arg_keys": ["q"]}, {"tool": "calc", "arg_keys": ["x"]}]
    swapped = [{"tool": "calc", "arg_keys": ["x"], "status": "ok"}, {"tool": "lookup", "arg_keys": ["q"], "status": "ok"}]
    s = score_trajectory(swapped, expected)
    assert s["tool_selection"] == 1.0 and s["order"] < 1.0 and s["passed"] is False

    padded = expected + [{"tool": "lookup", "arg_keys": ["q"]}, {"tool": "lookup", "arg_keys": ["q"]}]
    s2 = score_trajectory(padded, expected)
    assert s2["extra_steps"] == 2 and s2["efficiency"] == 0.5

    s3 = score_trajectory([{"tool": "lookup", "arg_keys": ["q"], "status": "ok"}], expected)
    assert s3["missing_tools"] == ["calc"] and s3["tool_selection"] == 0.5

    wrong_args = score_trajectory([{"tool": "lookup", "arg_keys": ["zzz"], "status": "ok"}], [{"tool": "lookup", "arg_keys": ["q"]}])
    assert wrong_args["arguments"] == 0.0


def test_failed_steps_fail_the_score_and_final_answer_check():
    from e2eai.agent_workflow import score_trajectory

    expected = [{"tool": "lookup", "arg_keys": []}]
    s = score_trajectory([{"tool": "lookup", "arg_keys": [], "status": "error"}], expected)
    assert s["passed"] is False
    ok = score_trajectory([{"tool": "lookup", "arg_keys": [], "status": "ok"}], expected,
                          final_answer="The total is 42", must_include=["42"])
    assert ok["final_answer_ok"] is True and ok["passed"] is True
    bad = score_trajectory([{"tool": "lookup", "arg_keys": [], "status": "ok"}], expected,
                           final_answer="no idea", must_include=["42"])
    assert bad["final_answer_ok"] is False and bad["passed"] is False
    assert "no idea" not in str(bad)


def test_routes_are_wired():
    from e2eai.main import app

    paths = app.openapi()["paths"]
    assert "post" in paths["/api/v1/agents/workflow/validate"]
    assert "post" in paths["/api/v1/agents/trajectory/score"]
