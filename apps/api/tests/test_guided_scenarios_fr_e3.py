"""FR-E3 guided scenarios with sample data and expected outcomes.

Deterministic/offline, no DB: a built-in catalog (HR-policy bot, "Why does my bot hallucinate?",
"Find the permission leak") plus a checker that grades a learner submission against outcomes derived
from the sample data. Sample data is synthetic; nothing is read from real documents or users.
"""

import pytest


def test_catalog_has_the_three_prd_scenarios_in_en_and_id():
    from e2eai.scenarios import get_scenario, list_scenarios

    ids = {s["id"] for s in list_scenarios()}
    assert {"hr-policy-bot", "why-does-my-bot-hallucinate", "find-the-permission-leak"} <= ids
    for s in list_scenarios():
        assert s["stage"] in {"plan", "data", "build", "test", "release", "operate", "improve"}
        assert s["title"]["en"] and s["title"]["id"] and s["steps"] and s["expected_outcomes"]
        assert "sample_data" not in s  # list view is a summary
    full = get_scenario("find-the-permission-leak")
    assert full["sample_data"]["retrievals"] and full["sample_data"]["documents"]
    with pytest.raises(KeyError):
        get_scenario("nope")


def test_hr_policy_scenario_grades_share_and_no_leak_outcomes():
    from e2eai.scenarios import check_scenario

    good = check_scenario("hr-policy-bot", {
        "andi": {"answered": True, "cited_doc_ids": ["doc-hr-policy"]},
        "budi": {"answered": False, "cited_doc_ids": []},
    })
    assert good["passed"] is True and all(c["passed"] for c in good["checks"])

    leaky = check_scenario("hr-policy-bot", {
        "andi": {"answered": True, "cited_doc_ids": ["doc-hr-policy"]},
        "budi": {"answered": True, "cited_doc_ids": ["doc-hr-policy"]},
    })
    assert leaky["passed"] is False
    failed = {c["id"] for c in leaky["checks"] if not c["passed"]}
    assert failed == {"budi_gets_nothing"}
    assert all(c["hint"] for c in leaky["checks"] if not c["passed"])


def test_hallucination_scenario_scores_claim_identification():
    from e2eai.scenarios import check_scenario, get_scenario

    claims = get_scenario("why-does-my-bot-hallucinate")["sample_data"]["answer_claims"]
    assert len(claims) >= 3
    unsupported = [i for i, c in enumerate(claims) if not c["supported"]] if "supported" in claims[0] else None
    assert unsupported is None  # expected labels are not exposed to the learner

    ok = check_scenario("why-does-my-bot-hallucinate", {"unsupported_claims": [2], "root_cause": "retrieval_miss"})
    assert ok["passed"] is True
    wrong_claim = check_scenario("why-does-my-bot-hallucinate", {"unsupported_claims": [0], "root_cause": "retrieval_miss"})
    assert wrong_claim["passed"] is False
    wrong_cause = check_scenario("why-does-my-bot-hallucinate", {"unsupported_claims": [2], "root_cause": "bad_prompt"})
    assert wrong_cause["passed"] is False
    assert {c["id"] for c in wrong_cause["checks"] if not c["passed"]} == {"root_cause"}


def test_permission_leak_expected_answer_is_derived_from_acl_not_hardcoded():
    from e2eai.scenarios import check_scenario, get_scenario

    data = get_scenario("find-the-permission-leak")["sample_data"]
    asker = set(data["asker"]["principals"])
    leaked = sorted(
        r["result_id"] for r in data["retrievals"]
        if not (asker & set(next(d for d in data["documents"] if d["doc_id"] == r["doc_id"])["acl"]))
    )
    assert leaked  # at least one leak exists in the exercise
    assert all("acl_ok" not in r for r in data["retrievals"])  # answer key not exposed

    ok = check_scenario("find-the-permission-leak", {"leaked_result_ids": leaked})
    assert ok["passed"] is True
    miss = check_scenario("find-the-permission-leak", {"leaked_result_ids": leaked[:-1] + ["r-nonexistent"]})
    assert miss["passed"] is False
    over = check_scenario("find-the-permission-leak", {"leaked_result_ids": leaked + [data["retrievals"][0]["result_id"]]})
    assert over["passed"] is (data["retrievals"][0]["result_id"] in leaked)


def test_check_is_safe_on_malformed_submissions():
    from e2eai.scenarios import check_scenario

    for bad in ({}, {"leaked_result_ids": "r1"}, {"leaked_result_ids": [1, None]}, {"x": {"y": 1}}):
        res = check_scenario("find-the-permission-leak", bad)
        assert res["passed"] is False and isinstance(res["checks"], list)
    with pytest.raises(KeyError):
        check_scenario("missing", {})


def test_routes_are_wired():
    from e2eai.main import app

    paths = app.openapi()["paths"]
    assert "get" in paths["/api/v1/learn/scenarios"]
    assert "get" in paths["/api/v1/learn/scenarios/{scenario_id}"]
    assert "post" in paths["/api/v1/learn/scenarios/{scenario_id}/check"]
