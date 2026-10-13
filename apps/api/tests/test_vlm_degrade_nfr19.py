"""NFR-19: the optional VLM add-on degrades (baseline parse stays indexed) instead of failing ingestion."""

import asyncio

from e2eai.vlm_enrichment import build_vlm_enrichment_plan, run_vlm_enrichment

PLAN = build_vlm_enrichment_plan(
    document_id="d1", version_id="v1", enabled=True,
    selected_pages=[{"page": 2, "reasons": ["figure_heavy"]}, {"page": 5, "reasons": ["low_confidence_parse"]}],
)


class Client:
    def __init__(self, behaviour):
        self.behaviour, self.calls = behaviour, []

    async def describe_page(self, *, document_id, version_id, page):
        self.calls.append(page)
        out = self.behaviour(page)
        if isinstance(out, BaseException):
            raise out
        return out


def run(client, plan=PLAN):
    return asyncio.run(run_vlm_enrichment(plan, client))


def test_all_pages_described_become_derived_chunks():
    c = Client(lambda p: {"text": f"figure on page {p}", "figure_object_key": f"k{p}", "api_key": "sk-secret"})
    out = run(c)
    assert out["status"] == "ok" and out["failed_pages"] == []
    assert [ch["page"] for ch in out["chunks"]] == [2, 5]
    assert all(ch["kind"] == "vlm" and ch["permissions"]["inherits_from"] == "document" for ch in out["chunks"])
    assert "sk-secret" not in repr(out)


def test_vlm_outage_degrades_without_raising_and_stops_calling_after_first_outage():
    c = Client(lambda p: ConnectionError("vlm down at http://vlm.internal:8000 key=sk-secret"))
    out = run(c)
    assert out["status"] == "degraded" and out["chunks"] == []
    assert out["failed_pages"] == [2, 5]
    assert c.calls == [2]  # fail fast: no point hammering a down upstream
    assert out["reason"] == "vlm_unavailable"
    assert "vlm.internal" not in repr(out) and "sk-secret" not in repr(out)


def test_partial_failure_keeps_successful_pages():
    c = Client(lambda p: {"text": "ok"} if p == 2 else TimeoutError("slow"))
    out = run(c)
    assert out["status"] == "degraded" and [ch["page"] for ch in out["chunks"]] == [2]
    assert out["failed_pages"] == [5]


def test_disabled_plan_does_not_call_the_model():
    c = Client(lambda p: {"text": "x"})
    plan = build_vlm_enrichment_plan(document_id="d1", version_id="v1", enabled=False, selected_pages=[{"page": 2}])
    out = run(c, plan)
    assert out["status"] == "skipped" and c.calls == [] and out["chunks"] == []
