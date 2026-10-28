"""FR-T2: the eval route can run the offline adapter or the real Ragas service; anything else is a clear 400."""

import asyncio

import pytest

from e2eai import ragas_http_adapter
from e2eai.core.errors import AppError
from e2eai.eval_lab import LocalRagasAdapter, RunIn, resolve_eval_adapter


def test_the_offline_adapter_is_still_the_default_choice():
    assert RunIn(dataset_id="01a181b1-b892-7c87-95fd-c3a8292dd716").adapter == "ragas.local"
    assert isinstance(asyncio.run(resolve_eval_adapter("ragas.local")), LocalRagasAdapter)


def test_ragas_builds_the_http_adapter_with_a_per_run_key_and_the_requested_metrics(monkeypatch):
    seen = {}

    async def fake_build(settings, *, run_id, metrics=None, **_):
        seen.update(run_id=run_id, metrics=metrics)
        return "adapter-object"

    monkeypatch.setattr(ragas_http_adapter, "build_ragas_adapter", fake_build)
    adapter = asyncio.run(resolve_eval_adapter("ragas", metrics=["faithfulness"]))
    assert adapter == "adapter-object" and seen["metrics"] == ["faithfulness"] and len(seen["run_id"]) >= 16


def test_an_unknown_adapter_is_a_400_that_names_the_choices():
    with pytest.raises(AppError) as err:
        asyncio.run(resolve_eval_adapter("deepeval"))
    assert err.value.status == 400 and "ragas.local" in err.value.detail and "ragas" in err.value.detail


def test_the_run_request_accepts_an_optional_metric_list():
    body = RunIn(dataset_id="01a181b1-b892-7c87-95fd-c3a8292dd716", adapter="ragas", metrics=["faithfulness", "answer_relevancy"])
    assert body.metrics == ["faithfulness", "answer_relevancy"]
