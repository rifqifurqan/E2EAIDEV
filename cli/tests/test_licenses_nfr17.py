"""NFR-17: the license of every tool and model is shown before install; AGPL tools run as separate services only."""

from pathlib import Path

from typer.testing import CliRunner

from e2eai_wizard import generate, models
from e2eai_wizard.cli import app
from e2eai_wizard.licenses import TOOL_LICENSES, license_report, render_license_report
from e2eai_wizard.services import SERVICES, enabled_services

ROOT = Path(__file__).resolve().parents[2]


def _answers(**over):
    a = generate.default_answers(tier="lite", ports={s.name: s.default_port for s in SERVICES},
                                 host_ollama=False, gpu=False)
    a.update(over)
    return a


def test_every_installable_service_has_a_license_entry():
    missing = [s.name for s in SERVICES if s.name not in TOOL_LICENSES]
    assert missing == []
    for name, info in TOOL_LICENSES.items():
        assert info.spdx and info.license_class in {"permissive", "copyleft-separate", "restrictive"}, name


def test_report_lists_enabled_tools_and_chosen_models_only():
    a = _answers(optional={"ollama": True, "vllm": False, "tei-embed": False, "tei-rerank": False, "keycloak": False})
    catalog = models.load_catalog(ROOT)
    models.apply_selection(a, {"chat": ["llama3.2:3b"], "embedding": ["bge-m3"], "reranker": [], "external": []}
                           if "reranker" in models.ROLES else
                           {r: [] for r in models.ROLES} | {"chat": ["llama3.2:3b"], "embedding": ["bge-m3"], "external": []},
                           catalog)
    rows = license_report(a, catalog)
    names = {r["name"] for r in rows}
    assert {"postgres", "ollama", "llama3.2:3b", "bge-m3"} <= names
    assert "keycloak" not in names and "vllm" not in names


def test_restrictive_model_license_is_flagged_for_review():
    a = _answers()
    catalog = models.load_catalog(ROOT)
    sel = {r: [] for r in models.ROLES} | {"chat": ["gemma3:4b"], "external": []}
    models.apply_selection(a, sel, catalog)
    row = next(r for r in license_report(a, catalog) if r["name"] == "gemma3:4b")
    assert row["kind"] == "model" and row["review"] is True and "conditions" in row["note"]


def test_permissive_tool_needs_no_review_and_report_marks_unverified_data():
    a = _answers()
    row = next(r for r in license_report(a, models.load_catalog(ROOT)) if r["name"] == "postgres")
    assert row["kind"] == "tool" and row["review"] is False
    text = render_license_report(license_report(a, models.load_catalog(ROOT)))
    assert "re-verify" in text.lower()


def test_external_api_models_are_listed_with_provider_terms_notice():
    a = _answers()
    catalog = models.load_catalog(ROOT)
    sel = {r: [] for r in models.ROLES} | {"external": [{"provider": next(iter(models.EXTERNAL_PROVIDERS)), "model": "x-model"}]}
    models.apply_selection(a, sel, catalog)
    rows = license_report(a, catalog)
    ext = next(r for r in rows if r["name"].endswith("x-model"))
    assert ext["kind"] == "external-model" and ext["review"] is True and "provider terms" in ext["note"].lower()


def test_licenses_cli_prints_report_without_secrets():
    r = CliRunner().invoke(app, ["licenses"])
    assert r.exit_code == 0, r.output
    assert "postgres" in r.output.lower() and "License" in r.output
    assert "password" not in r.output.lower()


def test_init_shows_licenses_before_writing_any_file(tmp_path, monkeypatch):
    import shutil

    from e2eai_wizard import detect

    root = tmp_path
    (root / "deploy").mkdir()
    (root / "deploy" / "compose" / "seaweedfs").mkdir(parents=True)
    (root / "deploy" / "versions.lock").write_text("images:\n  postgres: pg@sha256:abc\n")
    shutil.copytree(ROOT / "catalog", root / "catalog")
    monkeypatch.setattr(detect, "hardware", lambda *_: detect.Hardware(cpus=8, ram_gb=16, disk_free_gb=100, gpu=None))
    monkeypatch.setattr(detect, "docker_version", lambda: "29.0")
    monkeypatch.setattr(detect, "host_ollama_version", lambda: None)
    monkeypatch.setattr(detect, "docker_volume_exists", lambda _: False)
    monkeypatch.setattr(detect, "docker_mem_gb", lambda: 4.8)

    written_at = []
    real_write = generate.write_all

    def spy(*args, **kwargs):
        written_at.append(True)
        return real_write(*args, **kwargs)

    monkeypatch.setattr(generate, "write_all", spy)
    printed_before_write = []
    import e2eai_wizard.cli as cli_mod

    real_print = cli_mod.out.print

    def spy_print(*args, **kwargs):
        if not written_at:
            printed_before_write.append(" ".join(str(a) for a in args))
        return real_print(*args, **kwargs)

    monkeypatch.setattr(cli_mod.out, "print", spy_print)
    result = CliRunner().invoke(app, ["init", "--yes", "--no-pull", "--root", str(root)])
    assert result.exit_code == 0, result.output
    assert written_at, "write_all was never called"
    assert any("License report" in line for line in printed_before_write)
