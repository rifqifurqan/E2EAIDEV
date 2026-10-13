"""FR-RL3: CI integration for eval suites in GitHub Actions / GitLab CI.

Deterministic, offline, static validation of the CI pipeline config. No network,
no running pipeline: we parse the committed workflow files and the canonical gate
script and assert they run the eval/release/security suites and fail the pipeline
on regression (no continue-on-error / allow_failure escape hatches), with no
secrets and no floating/`latest` pins.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
GH_WORKFLOW = REPO / ".github" / "workflows" / "eval-suites.yml"
GITLAB_CI = REPO / ".gitlab-ci.yml"
GATE_SCRIPT = REPO / "scripts" / "ci_eval_gate.py"
CONFTEST = REPO / "apps" / "api" / "tests" / "conftest.py"


def _load_gate_module():
    spec = importlib.util.spec_from_file_location("ci_eval_gate", GATE_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------- #
# canonical gate script                                                       #
# --------------------------------------------------------------------------- #

def test_gate_script_exists_and_lists_eval_release_security_suites():
    assert GATE_SCRIPT.is_file(), "scripts/ci_eval_gate.py must exist"
    gate = _load_gate_module()
    suites = list(gate.EVAL_SUITES)
    # every listed suite file must actually exist under apps/api/tests
    tests_dir = REPO / "apps" / "api" / "tests"
    for name in suites:
        assert (tests_dir / name).is_file(), f"gate references missing suite {name}"
    joined = " ".join(suites)
    # must cover eval, release-gate, and red-team security regressions
    assert "test_us_eval_lab_p0.py" in suites
    assert "test_us_release_gates_p1.py" in suites
    assert "test_us_security_red_team_p1.py" in suites
    assert "release" in joined and "security_red_team" in joined


def test_gate_command_runs_pytest_and_propagates_failure():
    gate = _load_gate_module()
    cmd = gate.pytest_command()
    # pytest invocation that fails the process on any regression (non-zero exit)
    assert "pytest" in cmd
    # suites passed to pytest (as test paths)
    joined = " ".join(cmd)
    for name in gate.EVAL_SUITES:
        assert name in joined


# --------------------------------------------------------------------------- #
# GitHub Actions                                                              #
# --------------------------------------------------------------------------- #

def test_github_workflow_runs_gate_and_fails_on_regression():
    assert GH_WORKFLOW.is_file(), ".github/workflows/eval-suites.yml must exist"
    text = GH_WORKFLOW.read_text(encoding="utf-8")
    wf = yaml.safe_load(text)

    # triggers: push + pull_request (YAML parses bare `on:` key as True)
    triggers = wf.get("on") or wf.get(True)
    assert triggers and "push" in triggers and "pull_request" in triggers

    jobs = wf["jobs"]
    for name, job in jobs.items():
        runner = job.get("runs-on", "")
        assert runner and not str(runner).endswith("-latest"), f"{name} uses floating runner {runner}"
        assert job.get("env", {}).get("E2EAI_SKIP_DB_TESTS") == "1"

    steps = [s for j in jobs.values() for s in j["steps"]]
    run_blocks = "\n".join(s.get("run", "") for s in steps)
    assert "ci_eval_gate.py" in run_blocks, "workflow must invoke the gate script"

    # no step is allowed to swallow a regression
    for s in steps:
        assert s.get("continue-on-error") not in (True, "true")

    # pinned actions only: no @main/@master/@latest floating refs
    for s in steps:
        uses = s.get("uses")
        if uses:
            ref = uses.split("@")[-1]
            assert ref not in ("main", "master", "latest"), f"unpinned action: {uses}"
            assert "@" in uses, f"action not pinned: {uses}"


# --------------------------------------------------------------------------- #
# GitLab CI                                                                   #
# --------------------------------------------------------------------------- #

def test_gitlab_ci_runs_gate_and_fails_on_regression():
    assert GITLAB_CI.is_file(), ".gitlab-ci.yml must exist"
    text = GITLAB_CI.read_text(encoding="utf-8")
    cfg = yaml.safe_load(text)
    assert cfg.get("variables", {}).get("E2EAI_SKIP_DB_TESTS") == "1"

    # pinned image, never :latest
    image = cfg.get("image") or next(
        (j["image"] for j in cfg.values() if isinstance(j, dict) and "image" in j),
        None,
    )
    assert image, ".gitlab-ci.yml must pin a container image"
    img_str = image if isinstance(image, str) else image.get("name", "")
    assert ":" in img_str and not img_str.endswith(":latest"), f"unpinned image: {img_str}"

    # a job script must invoke the gate script and must not allow_failure
    job_found = False
    for name, job in cfg.items():
        if not isinstance(job, dict) or "script" not in job:
            continue
        script = "\n".join(job["script"] if isinstance(job["script"], list) else [job["script"]])
        if "ci_eval_gate.py" in script:
            job_found = True
            assert job.get("allow_failure") not in (True, "true"), f"{name} allows failure"
    assert job_found, "no GitLab job invokes the gate script"


def test_hosted_ci_has_explicit_db_skip_boundary_for_offline_gate():
    assert CONFTEST.is_file(), "CI gate needs an explicit DB-skip boundary for hosted runners"
    text = CONFTEST.read_text(encoding="utf-8")
    assert "E2EAI_SKIP_DB_TESTS" in text
    assert "pytest.skip" in text
    assert "e2eai.db" in text


# --------------------------------------------------------------------------- #
# no secrets committed in either CI file                                      #
# --------------------------------------------------------------------------- #

def test_ci_files_contain_no_secrets():
    for f in (GH_WORKFLOW, GITLAB_CI):
        text = f.read_text(encoding="utf-8").lower()
        # no literal passwords/keys/tokens assigned inline
        for needle in ("password:", "api_key:", "secret_key:", "-----begin"):
            assert needle not in text, f"{f.name} appears to embed a secret ({needle})"
