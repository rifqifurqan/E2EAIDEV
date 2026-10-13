#!/usr/bin/env python3
"""FR-RL3: CI eval gate — run the eval/release/security suites and fail on regression.

Single source of truth for which suites gate a release in CI. Both the GitHub
Actions workflow (`.github/workflows/eval-suites.yml`) and the GitLab CI config
(`.gitlab-ci.yml`) invoke this script so the suite list never drifts between them.

The gated suites are deterministic/offline (no live stack, no secrets, no paid
services). A regression — a failed eval threshold, a permission leak, a red-team
miss, or a broken release gate — fails the pytest run, which exits non-zero and
fails the pipeline.

Run:  python scripts/ci_eval_gate.py        (exit 0 = pass, non-zero = regression)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
API_DIR = REPO / "apps" / "api"

# Eval / release / security regression suites that gate a release.
EVAL_SUITES: list[str] = [
    # Eval Lab + metrics
    "test_us_eval_lab_p0.py",
    "test_us_retrieval_metrics_p1.py",
    "test_us_evaluator_transparency_p1.py",
    "test_us_lab_cost_estimate_p1.py",
    "test_us_lab_compare_reports_p1.py",
    "test_us_judging_modes_p1.py",
    "test_us_benchmark_runner_p1.py",
    "test_us_doc_understanding_p1.py",
    # Security red-team
    "test_us_security_red_team_p1.py",
    # Release gates + bundle
    "test_us_release_gates_p1.py",
    "test_us_release_bundle_p0.py",
]


def pytest_command() -> list[str]:
    """The pytest invocation run by the gate (fails the process on any regression)."""
    return ["uv", "run", "pytest", "-q", "-rs", *(f"tests/{s}" for s in EVAL_SUITES)]


def main() -> int:
    print(f"CI eval gate: running {len(EVAL_SUITES)} eval/release/security suites")
    result = subprocess.run(pytest_command(), cwd=API_DIR)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
