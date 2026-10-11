"""FR-B3 Structured-output tests: JSON/schema validity rate per model."""

from e2eai.eval_lab import evaluate_structured_output_validity


INVOICE_SCHEMA = {
    "type": "object",
    "required": ["invoice_id", "total", "currency", "line_items"],
    "properties": {
        "invoice_id": {"type": "string"},
        "total": {"type": "number"},
        "currency": {"type": "string", "enum": ["IDR", "USD"]},
        "line_items": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["description", "amount"],
                "properties": {
                    "description": {"type": "string"},
                    "amount": {"type": "number"},
                },
                "additionalProperties": False,
            },
        },
    },
    "additionalProperties": False,
}


def test_structured_output_validity_reports_rate_per_model_without_raw_outputs():
    report = evaluate_structured_output_validity(
        [
            {
                "item_id": "invoice-1",
                "model": "qwen3-8b",
                "output": '{"invoice_id":"INV-1","total":125000,"currency":"IDR","line_items":[{"description":"support","amount":125000}]}',
            },
            {
                "item_id": "invoice-2",
                "model": "qwen3-8b",
                "output": '{"invoice_id":"INV-2","total":"125000","currency":"IDR","line_items":[]}',
            },
            {
                "item_id": "invoice-3",
                "model": "small-local",
                "output": '{"invoice_id":"INV-3","total":20,"currency":"EUR","line_items":[]}',
            },
            {
                "item_id": "invoice-4",
                "model": "small-local",
                "output": '{not-json',
            },
        ],
        schema=INVOICE_SCHEMA,
    )

    assert report["kind"] == "structured_output_validity"
    by_model = {row["model"]: row for row in report["models"]}
    assert by_model["qwen3-8b"] == {
        "model": "qwen3-8b",
        "attempts": 2,
        "valid": 1,
        "invalid_json": 0,
        "schema_invalid": 1,
        "validity_rate": 0.5,
    }
    assert by_model["small-local"]["attempts"] == 2
    assert by_model["small-local"]["valid"] == 0
    assert by_model["small-local"]["invalid_json"] == 1
    assert by_model["small-local"]["schema_invalid"] == 1
    assert by_model["small-local"]["validity_rate"] == 0.0

    item_results = {row["item_id"]: row for row in report["item_results"]}
    assert item_results["invoice-1"]["valid"] is True
    assert item_results["invoice-2"]["error_code"] == "schema_type_mismatch"
    assert item_results["invoice-3"]["error_code"] == "schema_enum_mismatch"
    assert item_results["invoice-4"]["error_code"] == "invalid_json"

    serialized = str(report)
    assert "INV-1" not in serialized
    assert "support" not in serialized
    assert "{not-json" not in serialized


def test_structured_output_validity_handles_missing_required_and_extra_fields():
    report = evaluate_structured_output_validity(
        [
            {"item_id": "missing", "model": "model-a", "output": '{"invoice_id":"INV-5","total":10,"currency":"IDR"}'},
            {
                "item_id": "extra",
                "model": "model-a",
                "output": '{"invoice_id":"INV-6","total":10,"currency":"IDR","line_items":[],"secret":"do-not-store"}',
            },
        ],
        schema=INVOICE_SCHEMA,
    )

    item_results = {row["item_id"]: row for row in report["item_results"]}
    assert item_results["missing"]["error_code"] == "schema_required_missing"
    assert item_results["extra"]["error_code"] == "schema_additional_property"
    assert "do-not-store" not in str(report)
