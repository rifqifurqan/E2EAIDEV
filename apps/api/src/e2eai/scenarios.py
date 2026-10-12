"""Guided scenarios with sample data and expected outcomes (FR-E3).

Deterministic/offline, no DB. All sample data is synthetic. The answer key is never part of the
returned scenario: expected outcomes are computed inside `check_scenario` (the permission-leak answer
is derived from the sample ACLs rather than hardcoded). Submissions are treated as untrusted input.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .auth import current_session
from .core.errors import AppError

_ASKER = {"user_id": "andi", "principals": ["user:andi", "team:finance"]}

_SCENARIOS: dict[str, dict[str, Any]] = {
    "hr-policy-bot": {
        "id": "hr-policy-bot",
        "stage": "build",
        "title": {"en": "Build an HR-policy bot", "id": "Bangun bot kebijakan HR"},
        "summary": {
            "en": "Share a leave policy with Andi only, then confirm Andi gets a cited answer and Budi gets nothing.",
            "id": "Bagikan kebijakan cuti hanya ke Andi, lalu pastikan Andi mendapat jawaban bersitasi dan Budi tidak.",
        },
        "steps": [
            {"en": "Upload the sample leave policy.", "id": "Unggah contoh kebijakan cuti."},
            {"en": "Share it with Andi only.", "id": "Bagikan hanya ke Andi."},
            {"en": "Ask the bot as Andi, then as Budi.", "id": "Tanya bot sebagai Andi, lalu sebagai Budi."},
        ],
        "expected_outcomes": [
            {"id": "andi_gets_cited_answer", "en": "Andi receives an answer citing the policy.",
             "id": "Andi menerima jawaban yang mengutip kebijakan."},
            {"id": "budi_gets_nothing", "en": "Budi receives no answer and no citations.",
             "id": "Budi tidak menerima jawaban dan sitasi."},
        ],
        "sample_data": {
            "documents": [{"doc_id": "doc-hr-policy", "title": "Leave policy (sample)", "text": "Annual leave is 12 working days."}],
            "question": "How many days of annual leave do I get?",
            "submission_shape": {"andi": {"answered": True, "cited_doc_ids": []}, "budi": {"answered": False, "cited_doc_ids": []}},
        },
    },
    "why-does-my-bot-hallucinate": {
        "id": "why-does-my-bot-hallucinate",
        "stage": "test",
        "title": {"en": "Why does my bot hallucinate?", "id": "Mengapa bot saya berhalusinasi?"},
        "summary": {
            "en": "Compare an answer with the retrieved passages, find the unsupported claim, and name the root cause.",
            "id": "Bandingkan jawaban dengan passage hasil retrieval, temukan klaim tanpa dukungan, dan sebutkan akar masalahnya.",
        },
        "steps": [
            {"en": "Read the retrieved passages.", "id": "Baca passage hasil retrieval."},
            {"en": "Mark claims that no passage supports.", "id": "Tandai klaim yang tidak didukung passage."},
            {"en": "Choose the root cause.", "id": "Pilih akar masalahnya."},
        ],
        "expected_outcomes": [
            {"id": "unsupported_claims", "en": "Exactly the unsupported claim(s) are identified.",
             "id": "Tepat klaim tanpa dukungan yang teridentifikasi."},
            {"id": "root_cause", "en": "The root cause is identified.", "id": "Akar masalah teridentifikasi."},
        ],
        "sample_data": {
            "question": "What is the travel reimbursement limit and who approves it?",
            "retrieved_passages": [
                {"passage_id": "p1", "text": "Domestic travel is reimbursed up to IDR 2,000,000 per trip."},
                {"passage_id": "p2", "text": "Claims are submitted within 14 days after the trip."},
            ],
            "answer_claims": [
                {"index": 0, "text": "Domestic travel is reimbursed up to IDR 2,000,000 per trip."},
                {"index": 1, "text": "Claims must be submitted within 14 days."},
                {"index": 2, "text": "The department head approves every claim."},
            ],
            "root_cause_options": ["retrieval_miss", "bad_prompt", "stale_document", "model_too_small"],
        },
    },
    "find-the-permission-leak": {
        "id": "find-the-permission-leak",
        "stage": "test",
        "title": {"en": "Find the permission leak", "id": "Temukan kebocoran izin"},
        "summary": {
            "en": "Given the asker's principals, document ACLs, and retrieval results, list the results that should not have been returned.",
            "id": "Dengan principal penanya, ACL dokumen, dan hasil retrieval, daftarkan hasil yang seharusnya tidak dikembalikan.",
        },
        "steps": [
            {"en": "Read the asker's principals.", "id": "Baca principal penanya."},
            {"en": "Compare each result's document ACL.", "id": "Bandingkan ACL dokumen tiap hasil."},
            {"en": "Report the leaked result ids.", "id": "Laporkan id hasil yang bocor."},
        ],
        "expected_outcomes": [
            {"id": "leaked_result_ids", "en": "Exactly the leaked results are reported.",
             "id": "Tepat hasil yang bocor yang dilaporkan."},
        ],
        "sample_data": {
            "asker": _ASKER,
            "documents": [
                {"doc_id": "d1", "title": "Finance budget (sample)", "acl": ["team:finance"]},
                {"doc_id": "d2", "title": "Executive salaries (sample)", "acl": ["team:exec"]},
                {"doc_id": "d3", "title": "Public handbook (sample)", "acl": ["org:all", "user:andi"]},
                {"doc_id": "d4", "title": "HR investigations (sample)", "acl": ["team:hr"]},
            ],
            "retrievals": [
                {"result_id": "r1", "doc_id": "d1", "snippet": "FY27 budget ..."},
                {"result_id": "r2", "doc_id": "d2", "snippet": "CEO compensation ..."},
                {"result_id": "r3", "doc_id": "d3", "snippet": "Working hours ..."},
                {"result_id": "r4", "doc_id": "d4", "snippet": "Case 14 ..."},
            ],
        },
    },
}


def list_scenarios() -> list[dict[str, Any]]:
    return [
        {k: s[k] for k in ("id", "stage", "title", "summary", "steps", "expected_outcomes")}
        for s in _SCENARIOS.values()
    ]


def get_scenario(scenario_id: str) -> dict[str, Any]:
    return _SCENARIOS[scenario_id]


def _check(cid: str, passed: bool, hint: str) -> dict[str, Any]:
    return {"id": cid, "passed": passed, "hint": None if passed else hint}


def _str_list(value: Any) -> list[str] | None:
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        return None
    return value


def _int_list(value: Any) -> list[int] | None:
    if not isinstance(value, list) or not all(isinstance(x, int) and not isinstance(x, bool) for x in value):
        return None
    return value


def _check_hr(sub: dict) -> list[dict]:
    andi, budi = sub.get("andi"), sub.get("budi")
    andi = andi if isinstance(andi, dict) else {}
    budi = budi if isinstance(budi, dict) else {}
    andi_cites = _str_list(andi.get("cited_doc_ids")) or []
    budi_cites = _str_list(budi.get("cited_doc_ids")) or []
    return [
        _check("andi_gets_cited_answer", andi.get("answered") is True and "doc-hr-policy" in andi_cites,
               "Share the policy with Andi, then ask again: the answer must cite doc-hr-policy."),
        _check("budi_gets_nothing", budi.get("answered") is False and not budi_cites,
               "Budi has no access: filter by permission inside the retrieval query, not after top-k."),
    ]


def _check_hallucination(sub: dict) -> list[dict]:
    # answer key: claim 2 (the approver) appears in no retrieved passage; the passages were simply
    # missing the approval rule, so retrieval did not surface the supporting document.
    chosen = _int_list(sub.get("unsupported_claims"))
    return [
        _check("unsupported_claims", chosen is not None and set(chosen) == {2},
               "Check each claim against the passages; mark only claims no passage supports."),
        _check("root_cause", sub.get("root_cause") == "retrieval_miss",
               "The answer asserts something no retrieved passage contains: look at retrieval before the prompt or model."),
    ]


def _check_leak(sub: dict) -> list[dict]:
    data = _SCENARIOS["find-the-permission-leak"]["sample_data"]
    principals = set(data["asker"]["principals"])
    acl = {d["doc_id"]: set(d["acl"]) for d in data["documents"]}
    expected = {r["result_id"] for r in data["retrievals"] if not (principals & acl.get(r["doc_id"], set()))}
    reported = _str_list(sub.get("leaked_result_ids"))
    return [
        _check("leaked_result_ids", reported is not None and set(reported) == expected,
               "A result leaks when none of the asker's principals appears in its document ACL."),
    ]


_CHECKERS: dict[str, Callable[[dict], list[dict]]] = {
    "hr-policy-bot": _check_hr,
    "why-does-my-bot-hallucinate": _check_hallucination,
    "find-the-permission-leak": _check_leak,
}


def check_scenario(scenario_id: str, submission: Any) -> dict[str, Any]:
    """Grade a learner submission. Unknown scenario -> KeyError; malformed input -> failed checks."""
    checker = _CHECKERS[scenario_id]
    checks = checker(submission if isinstance(submission, dict) else {})
    return {"scenario_id": scenario_id, "passed": all(c["passed"] for c in checks), "checks": checks}


class CheckIn(BaseModel):
    submission: dict[str, Any]


router = APIRouter(prefix="/api/v1/learn/scenarios", tags=["learn"])


@router.get("")
async def list_api(sess: dict = Depends(current_session)) -> dict[str, Any]:
    return {"scenarios": list_scenarios()}


@router.get("/{scenario_id}")
async def get_api(scenario_id: str, sess: dict = Depends(current_session)) -> dict[str, Any]:
    try:
        return get_scenario(scenario_id)
    except KeyError as exc:
        raise AppError(404, "Scenario not found") from exc


@router.post("/{scenario_id}/check")
async def check_api(scenario_id: str, body: CheckIn, sess: dict = Depends(current_session)) -> dict[str, Any]:
    try:
        return check_scenario(scenario_id, body.submission)
    except KeyError as exc:
        raise AppError(404, "Scenario not found") from exc
