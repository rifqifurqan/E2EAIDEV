"""FR-D16 Technical and maintenance manual parsing helpers."""

from e2eai.manual_understanding import build_manual_answer_context, extract_manual_procedure


def test_manual_procedure_keeps_step_figure_links_parts_specs_and_verbatim_warnings():
    blocks = [
        {"kind": "heading", "text": "Replace spindle bearing"},
        {"kind": "safety_warning", "level": "DANGER", "text": "DANGER: Disconnect power before servicing."},
        {"kind": "safety_warning", "level": "WARNING", "text": "WARNING: Wear cut-resistant gloves."},
        {"kind": "step", "text": "1. Remove the guard, see Fig. 4-2."},
        {"kind": "figure", "ref": "Fig. 4-2", "caption": "Spindle guard exploded view", "object_key": "sha256/fig-4-2.png"},
        {"kind": "step", "text": "2. Install bearing PN 6205-2RS and torque bolts to 12 Nm."},
        {"kind": "table", "title": "Parts and torque", "rows": [{"part_no": "6205-2RS", "torque": "12 Nm"}]},
    ]

    procedure = extract_manual_procedure(blocks, procedure_id="spindle-bearing")

    assert procedure["procedure_id"] == "spindle-bearing"
    assert procedure["title"] == "Replace spindle bearing"
    assert procedure["warnings"] == [
        {"level": "DANGER", "text": "DANGER: Disconnect power before servicing."},
        {"level": "WARNING", "text": "WARNING: Wear cut-resistant gloves."},
    ]
    assert procedure["steps"][0]["figure_refs"] == ["Fig. 4-2"]
    assert procedure["figures"] == {
        "Fig. 4-2": {"caption": "Spindle guard exploded view", "object_key": "sha256/fig-4-2.png"}
    }
    assert procedure["parts"] == [{"part_no": "6205-2RS", "source": "table:Parts and torque"}]
    assert procedure["specs"] == [{"name": "torque", "value": "12 Nm", "source": "table:Parts and torque"}]


def test_manual_answer_context_requires_verbatim_safety_warnings_and_flags_figure_only_values():
    procedure = {
        "procedure_id": "line-3-bearing",
        "title": "Replace line 3 bearing",
        "warnings": [{"level": "WARNING", "text": "WARNING: Lock out the machine."}],
        "steps": [{"text": "Tighten nut shown in Fig. 9.", "figure_refs": ["Fig. 9"]}],
        "figures": {"Fig. 9": {"caption": "Nut torque callout", "object_key": "sha256/fig-9.png"}},
        "parts": [{"part_no": "NUT-M20", "source": "figure:Fig. 9"}],
        "specs": [{"name": "torque", "value": "55 Nm", "source": "figure:Fig. 9"}],
    }

    context = build_manual_answer_context(procedure)

    assert context["required_verbatim_warnings"] == ["WARNING: Lock out the machine."]
    assert context["citation_targets"] == ["figure:Fig. 9"]
    assert context["figure_confirmation_required"] == [
        {"name": "torque", "value": "55 Nm", "source": "figure:Fig. 9"}
    ]
    serialized = str(context)
    assert "WARNING: Lock out the machine." in serialized
    assert "55 Nm" in serialized
