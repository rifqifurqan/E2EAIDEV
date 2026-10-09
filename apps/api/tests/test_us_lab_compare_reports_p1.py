"""FR-L1/FR-L2 Lab compare mode and saved/exportable reports."""

import asyncio

from sqlalchemy import delete, select

from e2eai.db import EvalDataset, EvalRun, sessions
from e2eai.eval_lab import (
    build_comparison_report,
    create_dataset,
    export_comparison_report_csv,
    export_comparison_report_pdf_bytes,
    save_comparison_report,
)


def test_build_comparison_report_records_reproducibility_metadata_and_delta():
    baseline = EvalRun(
        dataset_id=None,
        adapter="ragas.local",
        status="completed",
        metrics={"answer_correctness": 0.9, "latency_ms": 100, "items": 2},
        item_results=[],
        created_by="test",
    )
    candidate = EvalRun(
        dataset_id=None,
        adapter="deepeval.local",
        status="completed",
        metrics={"answer_correctness": 0.7, "latency_ms": 80, "items": 2},
        item_results=[],
        created_by="test",
    )

    report = build_comparison_report(
        baseline,
        candidate,
        threshold=0.1,
        config={"judge_model": "qwen3.5:4b", "temperature": 0},
        tool_versions={"ragas": "local", "deepeval": "local"},
        model_versions={"judge": "qwen3.5:4b"},
        random_seed=42,
    )

    assert report["regression"] is True
    assert report["delta"]["answer_correctness"] == -0.2
    assert report["baseline"]["adapter"] == "ragas.local"
    assert report["candidate"]["adapter"] == "deepeval.local"
    assert report["reproducibility"]["config"]["temperature"] == 0
    assert report["reproducibility"]["tool_versions"]["ragas"] == "local"
    assert report["reproducibility"]["model_versions"]["judge"] == "qwen3.5:4b"
    assert report["reproducibility"]["random_seed"] == 42


def test_comparison_report_exports_csv_and_pdf_bytes():
    baseline = EvalRun(adapter="a", status="completed", metrics={"score": 0.5}, item_results=[], created_by="test")
    candidate = EvalRun(adapter="b", status="completed", metrics={"score": 0.75}, item_results=[], created_by="test")
    report = build_comparison_report(baseline, candidate, threshold=0.1)

    csv_text = export_comparison_report_csv(report)
    pdf_bytes = export_comparison_report_pdf_bytes(report)

    assert "metric,baseline,candidate,delta" in csv_text
    assert "score,0.5,0.75,0.25" in csv_text
    assert pdf_bytes.startswith(b"%PDF-1.4")
    assert b"E2EAIDEV Comparison Report" in pdf_bytes


def test_save_comparison_report_versions_reports_using_eval_runs_table():
    async def run():
        async with sessions()() as session:
            await session.execute(delete(EvalRun))
            await session.execute(delete(EvalDataset))
            await session.commit()
            ds = await create_dataset(
                session,
                name="compare-smoke",
                source="manual",
                items=[{"question": "Q", "answer": "A", "expected_answer": "A"}],
                created_by="test",
            )
            baseline = EvalRun(dataset_id=ds.id, adapter="ragas.local", status="completed", metrics={"score": 1.0}, item_results=[], created_by="test")
            candidate = EvalRun(dataset_id=ds.id, adapter="promptfoo.local", status="completed", metrics={"score": 0.8}, item_results=[], created_by="test")
            session.add_all([baseline, candidate])
            await session.commit()

            first = await save_comparison_report(session, baseline=baseline, candidate=candidate, created_by="test")
            second = await save_comparison_report(session, baseline=baseline, candidate=candidate, created_by="test")

            assert first.adapter == "comparison.local"
            assert first.dataset_id == ds.id
            assert first.metrics["report_version"] == 1
            assert second.metrics["report_version"] == 2
            assert second.metrics["shareable"] is True
            assert second.item_results[0]["export_formats"] == ["csv", "pdf"]

            stored = (await session.scalars(select(EvalRun).where(EvalRun.adapter == "comparison.local"))).all()
            assert len(stored) == 2

    asyncio.run(run())
