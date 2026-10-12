"""Agent workflows (multi-step tool chains) with trajectory evaluation (FR-B5).

Deterministic/offline. A workflow is a bounded, dependency-ordered list of tool steps run through an
injected async tool runner (only allow-listed tools run; the first blocked/failed step stops the run).
The recorded trajectory keeps tool names, argument *keys*, and status only: never argument values,
tool outputs, or exception text. `score_trajectory` compares a trajectory with an expected one on tool
selection, order, arguments, efficiency, and an optional final-answer check.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .auth import current_session, require_scope
from .core.errors import AppError

MAX_STEPS = 25
MAX_TRAJECTORY = 200

ToolRunner = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


def validate_workflow(workflow: dict[str, Any]) -> dict[str, Any]:
    steps_in = workflow.get("steps") if isinstance(workflow, dict) else None
    if not isinstance(steps_in, list) or not steps_in:
        raise ValueError("workflow needs at least one step")
    if len(steps_in) > MAX_STEPS:
        raise ValueError(f"workflow has more than {MAX_STEPS} steps")
    steps: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in steps_in:
        if not isinstance(raw, dict):
            raise ValueError("step must be an object")
        sid, tool = raw.get("id"), raw.get("tool")
        if not isinstance(sid, str) or not sid.strip() or not isinstance(tool, str) or not tool.strip():
            raise ValueError("step needs a non-empty id and tool")
        if sid in seen:
            raise ValueError("duplicate step id")
        seen.add(sid)
        args = raw.get("args") or {}
        deps = raw.get("depends_on") or []
        if not isinstance(args, dict) or not isinstance(deps, list):
            raise ValueError("invalid args or depends_on")
        steps.append({"id": sid, "tool": tool, "args": args, "depends_on": [str(d) for d in deps]})
    for s in steps:
        if any(d not in seen for d in s["depends_on"]) or s["id"] in s["depends_on"]:
            raise ValueError("unknown or self dependency")
    return {"steps": _topological(steps)}


def _topological(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    done: set[str] = set()
    ordered: list[dict[str, Any]] = []
    remaining = list(steps)
    while remaining:
        ready = next((s for s in remaining if all(d in done for d in s["depends_on"])), None)
        if ready is None:
            raise ValueError("workflow has a dependency cycle")
        remaining.remove(ready)
        done.add(ready["id"])
        ordered.append(ready)
    return ordered


async def run_workflow(workflow: dict[str, Any], runner: ToolRunner, *, allowed_tools: Iterable[str]) -> dict[str, Any]:
    allowed = set(allowed_tools)
    wf = validate_workflow(workflow)
    trajectory: list[dict[str, Any]] = []
    status = "completed"
    for step in wf["steps"]:
        rec: dict[str, Any] = {"id": step["id"], "tool": step["tool"], "arg_keys": sorted(step["args"])}
        if step["tool"] not in allowed:
            rec.update(status="blocked", error_code="tool_not_allowed")
            trajectory.append(rec)
            status = "blocked"
            break
        try:
            result = await runner(step["tool"], step["args"])
        except Exception:  # noqa: BLE001 - exception text may carry data; record a code only
            rec.update(status="error", error_code="tool_error")
            trajectory.append(rec)
            status = "failed"
            break
        if isinstance(result, dict) and result.get("ok") is False:
            rec.update(status="error", error_code="tool_failed")
            trajectory.append(rec)
            status = "failed"
            break
        rec["status"] = "ok"
        trajectory.append(rec)
    return {"status": status, "steps": trajectory}


def _lcs(a: list[str], b: list[str]) -> int:
    table = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i, x in enumerate(a, 1):
        for j, y in enumerate(b, 1):
            table[i][j] = table[i - 1][j - 1] + 1 if x == y else max(table[i - 1][j], table[i][j - 1])
    return table[-1][-1]


def score_trajectory(
    actual: list[dict[str, Any]],
    expected: list[dict[str, Any]],
    *,
    final_answer: str | None = None,
    must_include: list[str] | None = None,
    ordered: bool = True,
    threshold: float = 0.8,
) -> dict[str, Any]:
    act_tools = [str(s.get("tool", "")) for s in actual]
    exp_tools = [str(s.get("tool", "")) for s in expected]
    remaining = list(act_tools)
    missing: list[str] = []
    for t in exp_tools:
        if t in remaining:
            remaining.remove(t)
        else:
            missing.append(t)
    n_exp = len(exp_tools)
    tool_selection = 1.0 if n_exp == 0 else (n_exp - len(missing)) / n_exp
    order = 1.0 if (not ordered or n_exp == 0) else _lcs(act_tools, exp_tools) / n_exp

    used: set[int] = set()
    arg_hits = 0
    for e in expected:
        for i, a in enumerate(actual):
            if i not in used and a.get("tool") == e.get("tool"):
                used.add(i)
                if sorted(a.get("arg_keys") or []) == sorted(e.get("arg_keys") or []):
                    arg_hits += 1
                break
    arguments = 1.0 if n_exp == 0 else arg_hits / n_exp
    if not actual:
        efficiency = 1.0 if n_exp == 0 else 0.0
    else:
        efficiency = min(1.0, n_exp / len(actual)) if n_exp else 0.0
    extra_steps = max(0, len(actual) - n_exp)

    if must_include:
        text = (final_answer or "").lower()
        final_ok = all(m.lower() in text for m in must_include)
    else:
        final_ok = True
    any_error = any(s.get("status") not in (None, "ok") for s in actual)
    score = round((tool_selection + order + arguments + efficiency) / 4, 4)
    passed = (
        score >= threshold and tool_selection == 1.0 and order == 1.0 and not any_error and final_ok
    )
    return {
        "tool_selection": round(tool_selection, 4), "order": round(order, 4),
        "arguments": round(arguments, 4), "efficiency": round(efficiency, 4),
        "score": score, "passed": passed, "extra_steps": extra_steps,
        "missing_tools": missing, "has_errors": any_error, "final_answer_ok": final_ok,
    }


class StepIn(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    tool: str = Field(min_length=1, max_length=100)
    args: dict[str, Any] = {}
    depends_on: list[str] = []


class WorkflowIn(BaseModel):
    steps: list[StepIn] = Field(max_length=MAX_STEPS + 1)


class TrajectoryStepIn(BaseModel):
    tool: str = Field(max_length=100)
    arg_keys: list[str] = []
    status: str | None = None


class ScoreIn(BaseModel):
    actual: list[TrajectoryStepIn] = Field(max_length=MAX_TRAJECTORY)
    expected: list[TrajectoryStepIn] = Field(max_length=MAX_TRAJECTORY)
    final_answer: str | None = Field(default=None, max_length=20_000)
    must_include: list[str] = Field(default=[], max_length=50)
    ordered: bool = True
    threshold: float = Field(default=0.8, ge=0.0, le=1.0)


router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


@router.post("/workflow/validate")
async def validate_workflow_api(body: WorkflowIn, sess: dict = Depends(current_session)) -> dict[str, Any]:
    """FR-B5: validate a tool-chain workflow and return its execution order (argument values are not echoed)."""
    require_scope(sess, "evals")
    try:
        wf = validate_workflow(body.model_dump())
    except ValueError as exc:
        raise AppError(400, str(exc)) from exc
    return {"steps": [
        {"id": s["id"], "tool": s["tool"], "depends_on": s["depends_on"], "arg_keys": sorted(s["args"])}
        for s in wf["steps"]
    ]}


@router.post("/trajectory/score")
async def score_trajectory_api(body: ScoreIn, sess: dict = Depends(current_session)) -> dict[str, Any]:
    """FR-B5: score a recorded agent trajectory against an expected one."""
    require_scope(sess, "evals")
    return score_trajectory(
        [s.model_dump() for s in body.actual], [s.model_dump() for s in body.expected],
        final_answer=body.final_answer, must_include=body.must_include,
        ordered=body.ordered, threshold=body.threshold,
    )
