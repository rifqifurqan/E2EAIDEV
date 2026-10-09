"""FR-L3 Lab tool catalog and license warnings."""

from e2eai.tool_catalog import license_warning, tool_catalog


def test_license_warning_flags_agpl_elv2_and_non_commercial():
    assert license_warning("AGPL-3.0") is True
    assert license_warning("Elastic License 2.0 / ELv2") is True
    assert license_warning("CC-BY-NC-4.0 non-commercial") is True
    assert license_warning("Apache-2.0") is False
    assert license_warning("MIT") is False


def test_tool_catalog_reports_maturity_resources_and_installed_status():
    catalog = tool_catalog(installed={"ragas", "promptfoo"})

    by_id = {tool["id"]: tool for tool in catalog["tools"]}
    assert by_id["ragas"]["installed"] is True
    assert by_id["promptfoo"]["installed"] is True
    assert by_id["deepeval"]["installed"] is False
    assert by_id["ragas"]["resource_need"] in {"low", "medium", "high"}
    assert by_id["ragas"]["maturity"] in {"stable", "maturing", "experimental"}
    assert "license_warning" in by_id["ragas"]
    assert catalog["summary"]["installed"] == 2
    assert catalog["summary"]["available"] >= 5


def test_tool_catalog_surfaces_restricted_license_warnings():
    catalog = tool_catalog(installed=set())
    warning_tools = [tool for tool in catalog["tools"] if tool["license_warning"]]

    assert warning_tools
    assert any("AGPL" in tool["license"] or "ELv2" in tool["license"] or "non-commercial" in tool["license"].lower()
               for tool in warning_tools)
    for tool in warning_tools:
        assert tool["warning"]
        assert "review" in tool["warning"].lower() or "separate service" in tool["warning"].lower()
