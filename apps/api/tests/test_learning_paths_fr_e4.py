"""FR-E4 role-based learning paths (AI engineer, evaluator, AI PM, compliance, platform).

Deterministic/offline, no DB: each path is an ordered list of steps that point at lifecycle stages,
FR-E3 guided scenarios, and doc sections. Referenced scenarios must exist; progress is computed from a
set of completed step ids supplied by the caller (nothing is stored here).
"""

import pytest


def test_five_prd_roles_have_ordered_bilingual_paths():
    from e2eai.learning_paths import get_path, list_paths

    ids = [p["id"] for p in list_paths()]
    assert set(ids) == {"ai-engineer", "evaluator", "ai-pm", "compliance", "platform"}
    for summary in list_paths():
        assert summary["title"]["en"] and summary["title"]["id"] and summary["step_count"] >= 3
        path = get_path(summary["id"])
        step_ids = [s["id"] for s in path["steps"]]
        assert len(step_ids) == len(set(step_ids))
        for s in path["steps"]:
            assert s["stage"] in {"plan", "data", "build", "test", "release", "operate", "improve"}
            assert s["title"]["en"] and s["title"]["id"]
    with pytest.raises(KeyError):
        get_path("nope")


def test_scenario_references_resolve_to_existing_scenarios():
    from e2eai.learning_paths import get_path, list_paths
    from e2eai.scenarios import get_scenario

    referenced = 0
    for summary in list_paths():
        for step in get_path(summary["id"])["steps"]:
            if step.get("scenario_id"):
                get_scenario(step["scenario_id"])  # raises KeyError if the reference is dangling
                referenced += 1
    assert referenced >= 3  # the three FR-E3 scenarios are wired into at least one path each


def test_progress_ignores_unknown_ids_and_points_to_next_step():
    from e2eai.learning_paths import get_path, path_progress

    steps = [s["id"] for s in get_path("evaluator")["steps"]]
    none = path_progress("evaluator", [])
    assert none["completed"] == 0 and none["percent"] == 0 and none["next_step"]["id"] == steps[0]

    part = path_progress("evaluator", [steps[0], "bogus-id", steps[0]])
    assert part["completed"] == 1 and part["total"] == len(steps) and part["next_step"]["id"] == steps[1]

    done = path_progress("evaluator", steps)
    assert done["percent"] == 100 and done["next_step"] is None
    with pytest.raises(KeyError):
        path_progress("nope", [])


def test_routes_are_wired():
    from e2eai.main import app

    paths = app.openapi()["paths"]
    assert "get" in paths["/api/v1/learn/paths"]
    assert "get" in paths["/api/v1/learn/paths/{path_id}"]
    assert "post" in paths["/api/v1/learn/paths/{path_id}/progress"]
