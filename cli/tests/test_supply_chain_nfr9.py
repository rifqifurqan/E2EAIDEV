"""NFR-9: pinned image digests, hash-locked dependencies, and an SBOM per release (CycloneDX)."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from e2eai_wizard.cli import app
from e2eai_wizard.supply_chain import (
    build_sbom,
    check_images_pinned,
    check_lock_hashes,
    parse_uv_lock,
    parse_versions_lock,
)

ROOT = Path(__file__).resolve().parents[2]

UV_LOCK = '''version = 1
[[package]]
name = "demo"
version = "1.0.0"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://x/demo-1.0.0.tar.gz", hash = "sha256:aaaa", size = 1 }
wheels = [
    { url = "https://x/demo-1.0.0-py3-none-any.whl", hash = "sha256:bbbb", size = 2 },
]

[[package]]
name = "e2eai-api"
version = "0.1.0"
source = { editable = "." }

[[package]]
name = "nohash"
version = "2.0.0"
source = { registry = "https://pypi.org/simple" }
wheels = [
    { url = "https://x/nohash-2.0.0-py3-none-any.whl", size = 2 },
]
'''

VERSIONS = """images:
  postgres: pgvector/pgvector:0.8.7-pg17-bookworm@sha256:ac08538c6f8b9904c33c8224c5e5706dbe760aca29db1d096972b4052c22a75d
  floaty: example/floaty:latest
  nodigest: example/nodigest:1.2.3
"""


def test_parse_uv_lock_extracts_packages_and_skips_the_project_itself():
    pkgs = parse_uv_lock(UV_LOCK)
    assert [p["name"] for p in pkgs] == ["demo", "nohash"]
    assert pkgs[0]["version"] == "1.0.0"
    assert pkgs[0]["hashes"] == ["sha256:aaaa", "sha256:bbbb"]


def test_lock_hash_check_reports_registry_packages_without_hashes():
    result = check_lock_hashes(parse_uv_lock(UV_LOCK))
    assert result["ok"] is False
    assert result["missing"] == ["nohash==2.0.0"]


def test_real_lock_files_are_fully_hash_locked():
    for lock in (ROOT / "apps" / "api" / "uv.lock", ROOT / "cli" / "uv.lock"):
        result = check_lock_hashes(parse_uv_lock(lock.read_text(encoding="utf-8")))
        assert result["ok"], (lock.name, result["missing"][:5])


def test_images_must_be_pinned_by_digest_and_not_floating():
    images = parse_versions_lock(VERSIONS)
    result = check_images_pinned(images)
    assert result["ok"] is False
    assert set(result["unpinned"]) == {"floaty", "nodigest"}
    assert "postgres" not in result["unpinned"]


def test_real_versions_lock_pins_every_image_by_digest():
    images = parse_versions_lock((ROOT / "deploy" / "versions.lock").read_text(encoding="utf-8"))
    assert images, "versions.lock has no images"
    assert check_images_pinned(images)["unpinned"] == []


def test_sbom_is_valid_cyclonedx_with_purls_hashes_and_image_digests():
    sbom = build_sbom(version="0.1.0", python_packages=parse_uv_lock(UV_LOCK), images=parse_versions_lock(VERSIONS))
    assert sbom["bomFormat"] == "CycloneDX" and sbom["specVersion"] == "1.5"
    assert sbom["metadata"]["component"]["version"] == "0.1.0"
    comps = {c["name"]: c for c in sbom["components"]}
    assert comps["demo"]["purl"] == "pkg:pypi/demo@1.0.0"
    assert comps["demo"]["type"] == "library"
    assert {h["alg"] for h in comps["demo"]["hashes"]} == {"SHA-256"}
    assert comps["demo"]["hashes"][0]["content"] == "aaaa"
    pg = comps["pgvector/pgvector"]
    assert pg["type"] == "container" and pg["version"] == "0.8.7-pg17-bookworm"
    assert pg["hashes"][0]["content"].startswith("ac08538c")
    assert len({c["bom-ref"] for c in sbom["components"]}) == len(sbom["components"])
    json.dumps(sbom)  # serialisable


def test_sbom_has_no_timestamp_or_machine_specific_data_so_it_is_reproducible():
    a = build_sbom(version="1", python_packages=parse_uv_lock(UV_LOCK), images=parse_versions_lock(VERSIONS))
    b = build_sbom(version="1", python_packages=parse_uv_lock(UV_LOCK), images=parse_versions_lock(VERSIONS))
    assert a == b
    assert "timestamp" not in json.dumps(a) and "serialNumber" not in a


def test_sbom_cli_writes_a_file_and_fails_on_unpinned_inputs(tmp_path):
    out = tmp_path / "sbom.json"
    r = CliRunner().invoke(app, ["sbom", "--output", str(out), "--version", "0.1.0"])
    assert r.exit_code == 0, r.output
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["bomFormat"] == "CycloneDX" and len(data["components"]) > 50


def test_sbom_cli_fails_when_an_image_is_not_pinned(tmp_path):
    bad = tmp_path / "versions.lock"
    bad.write_text(VERSIONS, encoding="utf-8")
    r = CliRunner().invoke(app, ["sbom", "--output", str(tmp_path / "x.json"), "--versions-lock", str(bad)])
    assert r.exit_code == 1
    assert "floaty" in r.output
    assert not (tmp_path / "x.json").exists()
