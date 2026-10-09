"""FR-T13 Document-understanding test set: table QA, chart QA, figure/diagram QA,
OCR character-error-rate, and safety-warning-included checks.

Tests are deterministic/offline — no model calls, no secrets, no network.
"""

import asyncio
import json

from sqlalchemy import delete, select

from e2eai.doc_understanding import (
    character_error_rate,
    evaluate_doc_understanding,
    score_items,
)
from e2eai.db import EvalDataset, EvalRun, sessions


# ---------------------------------------------------------------------------
# 1. Pure metric: character_error_rate (Levenshtein-based CER)
# ---------------------------------------------------------------------------

def test_character_error_rate_exact_match():
    assert character_error_rate("hello world", "hello world") == 0.0


def test_character_error_rate_completely_wrong():
    # Totally different strings: CER capped at 1.0
    assert character_error_rate("abc", "xyz") == 1.0


def test_character_error_rate_partial():
    # "hello" vs "helo" — 1 deletion out of 5 reference chars = 0.2
    assert character_error_rate("hello", "helo") == 0.2


def test_character_error_rate_empty_reference():
    # Empty reference with non-empty hypothesis => CER = 1.0
    assert character_error_rate("", "something") == 1.0


def test_character_error_rate_both_empty():
    assert character_error_rate("", "") == 0.0


# ---------------------------------------------------------------------------
# 2. Pure metric: score_items covers all five item kinds
# ---------------------------------------------------------------------------

def test_score_items_table_qa():
    items = [
        {"kind": "table_qa", "expected": "42.5", "actual": "42.5"},
        {"kind": "table_qa", "expected": "100", "actual": "99"},
    ]
    result = score_items(items)
    assert result["table_qa"]["total"] == 2
    assert result["table_qa"]["correct"] == 1
    assert result["table_qa"]["accuracy"] == 0.5


def test_score_items_chart_qa():
    items = [
        {"kind": "chart_qa", "expected": "Revenue: $5M", "actual": "Revenue: $5M"},
        {"kind": "chart_qa", "expected": "Growth: 12%", "actual": "Growth: 12%"},
        {"kind": "chart_qa", "expected": "Loss: $1M", "actual": "Loss: $2M"},
    ]
    result = score_items(items)
    assert result["chart_qa"]["total"] == 3
    assert result["chart_qa"]["correct"] == 2
    assert round(result["chart_qa"]["accuracy"], 4) == 0.6667


def test_score_items_figure_qa():
    items = [
        {"kind": "figure_qa", "expected": "flowchart", "actual": "flowchart"},
        {"kind": "figure_qa", "expected": "sequence diagram", "actual": "state diagram"},
    ]
    result = score_items(items)
    assert result["figure_qa"]["total"] == 2
    assert result["figure_qa"]["correct"] == 1
    assert result["figure_qa"]["accuracy"] == 0.5


def test_score_items_ocr_cer():
    items = [
        {"kind": "ocr", "expected": "hello world", "actual": "hello world"},
        {"kind": "ocr", "expected": "hello", "actual": "helo"},
    ]
    result = score_items(items)
    assert result["ocr"]["total"] == 2
    assert result["ocr"]["mean_cer"] == 0.1  # (0.0 + 0.2) / 2


def test_score_items_safety_warning():
    items = [
        {
            "kind": "safety_warning",
            "expected_warnings": ["DANGER: High voltage", "WARNING: Hot surface"],
            "actual_text": "This manual covers DANGER: High voltage areas and WARNING: Hot surface zones.",
        },
        {
            "kind": "safety_warning",
            "expected_warnings": ["CAUTION: Wear gloves"],
            "actual_text": "Please follow safety procedures.",
        },
    ]
    result = score_items(items)
    assert result["safety_warning"]["total"] == 2
    assert result["safety_warning"]["all_included"] == 1
    assert result["safety_warning"]["inclusion_rate"] == 0.5


def test_score_items_mixed_kinds():
    """All five kinds in one batch produce per-kind metrics."""
    items = [
        {"kind": "table_qa", "expected": "10", "actual": "10"},
        {"kind": "chart_qa", "expected": "20", "actual": "20"},
        {"kind": "figure_qa", "expected": "pie", "actual": "pie"},
        {"kind": "ocr", "expected": "test", "actual": "test"},
        {"kind": "safety_warning", "expected_warnings": ["DANGER"], "actual_text": "DANGER noted."},
    ]
    result = score_items(items)
    assert result["table_qa"]["accuracy"] == 1.0
    assert result["chart_qa"]["accuracy"] == 1.0
    assert result["figure_qa"]["accuracy"] == 1.0
    assert result["ocr"]["mean_cer"] == 0.0
    assert result["safety_warning"]["inclusion_rate"] == 1.0


# ---------------------------------------------------------------------------
# 3. DB-backed: evaluate_doc_understanding stores a safe EvalRun
# ---------------------------------------------------------------------------

def test_evaluate_doc_understanding_stores_safe_eval_run():
    """Stored item_results contain only metric numbers and kind labels — never
    raw table text, chart values, OCR text, warning text, document snippets,
    or answers."""
    async def run():
        async with sessions()() as session:
            await session.execute(delete(EvalRun))
            await session.execute(delete(EvalDataset))
            await session.commit()

            items = [
                {"kind": "table_qa", "expected": "42.5", "actual": "42.5"},
                {"kind": "table_qa", "expected": "secret torque 150Nm", "actual": "wrong"},
                {"kind": "chart_qa", "expected": "Revenue: $5M", "actual": "Revenue: $5M"},
                {"kind": "figure_qa", "expected": "flowchart", "actual": "flowchart"},
                {"kind": "ocr", "expected": "confidential serial ABC-123", "actual": "confidential serial ABC-123"},
                {
                    "kind": "safety_warning",
                    "expected_warnings": ["DANGER: Disconnect power before servicing"],
                    "actual_text": "Step 1: DANGER: Disconnect power before servicing. Step 2: Open panel.",
                },
            ]

            eval_run = await evaluate_doc_understanding(
                session,
                name="doc-understanding-smoke",
                items=items,
                created_by="test",
            )

            assert eval_run.adapter == "doc-understanding.local"
            assert eval_run.status == "completed"

            # Metrics contain per-kind summaries
            metrics = eval_run.metrics
            assert metrics["table_qa"]["total"] == 2
            assert metrics["table_qa"]["correct"] == 1
            assert metrics["chart_qa"]["accuracy"] == 1.0
            assert metrics["figure_qa"]["accuracy"] == 1.0
            assert metrics["ocr"]["mean_cer"] == 0.0
            assert metrics["safety_warning"]["inclusion_rate"] == 1.0

            # item_results have safe fields only
            assert len(eval_run.item_results) == 6
            for ir in eval_run.item_results:
                assert "kind" in ir
                assert "index" in ir
                # No raw content stored
                assert "expected" not in ir
                assert "actual" not in ir
                assert "actual_text" not in ir
                assert "expected_warnings" not in ir

            # Serialized storage must not contain any raw document content
            serialized = json.dumps(eval_run.metrics) + json.dumps(eval_run.item_results)
            for forbidden in [
                "42.5", "secret torque", "150Nm", "Revenue: $5M",
                "flowchart", "confidential serial", "ABC-123",
                "Disconnect power", "Open panel",
            ]:
                assert forbidden not in serialized, f"Leaked: {forbidden}"

            # Verify it was persisted
            stored = (await session.scalars(
                select(EvalRun).where(EvalRun.adapter == "doc-understanding.local")
            )).all()
            assert len(stored) == 1

    asyncio.run(run())


def test_evaluate_doc_understanding_empty_items():
    """Empty item list still produces a valid run with zero counts."""
    async def run():
        async with sessions()() as session:
            await session.execute(delete(EvalRun))
            await session.execute(delete(EvalDataset))
            await session.commit()

            eval_run = await evaluate_doc_understanding(
                session,
                name="doc-understanding-empty",
                items=[],
                created_by="test",
            )
            assert eval_run.adapter == "doc-understanding.local"
            assert eval_run.status == "completed"
            assert eval_run.metrics["items"] == 0
            assert eval_run.item_results == []

    asyncio.run(run())
