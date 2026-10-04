import socket
import stat
import sys
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from e2eai_wizard import detect, generate
from e2eai_wizard.cli import app
from e2eai_wizard.services import SERVICES, enabled_services


# --- ports -----------------------------------------------------------------

def test_suggest_port_skips_busy_and_taken_ports():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        busy = s.getsockname()[1]
        taken = {busy + 1}
        assert detect.port_in_use(busy)
        port = detect.suggest_port(busy, taken)
        assert port > busy + 1 and not detect.port_in_use(port)


# --- secrets ---------------------------------------------------------------

def test_generated_secrets_are_long_and_url_safe():
    s = generate.new_secret()
    assert len(s) >= 32 and generate.validate_secret(s) is None
    assert generate.new_secret(prefix="sk-").startswith("sk-")


@pytest.mark.parametrize("bad", ["short", "has space in it 123", "dollar$sign1234567", "quote'1234567890ab", "hash#12345678901234"])
def test_validate_secret_rejects_short_or_unsafe(bad):
    assert generate.validate_secret(bad) is not None


# --- tier ------------------------------------------------------------------

@pytest.mark.parametrize("ram,expected", [(16, "lite"), (22, "lite"), (47.9, "lite"), (64, "standard"), (128, "standard")])
def test_recommend_tier(ram, expected):
    assert detect.recommend_tier(ram_gb=ram) == expected


# --- rendering -------------------------------------------------------------

def _answers(**over):
    a = generate.default_answers(
        tier="lite", ports={n: p for n, p in ((s.name, s.default_port) for s in SERVICES)},
        host_ollama=False, gpu=False,
    )
    a.update(over)
    return a


def test_env_has_profiles_images_and_every_compose_variable():
    a = _answers(optional={"ollama": True, "keycloak": False, "tei-embed": False, "tei-rerank": False})
    env = generate.render_env(a, images={"postgres": "img@sha256:x"})
    assert "COMPOSE_PROFILES=ollama\n" in env
    assert "E2EAI_IMAGE_POSTGRES=img@sha256:x" in env
    assert "BIND_ADDRESS=127.0.0.1" in env
    for key in generate.REQUIRED_ENV_KEYS:
        assert f"\n{key}=" in "\n" + env, key


def test_host_ollama_means_no_ollama_container():
    a = _answers(host_ollama=True)
    assert "ollama" not in enabled_services(a)


def test_config_references_secrets_never_inlines_them():
    a = _answers()
    cfg = yaml.safe_load(generate.render_config(a))
    text = generate.render_config(a)
    for value in a["secrets"].values():
        assert value not in text
    assert cfg["secrets"]["postgres_password"] == "env:POSTGRES_PASSWORD"
    assert cfg["tier"] == "lite" and cfg["components"]["job_engine"] == "celery"


# --- writing files ---------------------------------------------------------

def _repo(tmp_path):
    (tmp_path / "deploy" / "compose" / "seaweedfs").mkdir(parents=True)
    (tmp_path / "deploy" / "versions.lock").write_text("images:\n  postgres: pg@sha256:abc\n")
    (tmp_path / "catalog").mkdir()
    real = Path(__file__).resolve().parents[2] / "catalog" / "models.yaml"
    (tmp_path / "catalog" / "models.yaml").write_text(real.read_text())
    return tmp_path


def test_write_refuses_to_overwrite_without_force(tmp_path):
    root = _repo(tmp_path)
    generate.write_all(root, _answers(), force=False)
    with pytest.raises(FileExistsError):
        generate.write_all(root, _answers(), force=False)


def test_write_with_force_backs_up_existing_env(tmp_path):
    root = _repo(tmp_path)
    generate.write_all(root, _answers(), force=False)
    generate.write_all(root, _answers(), force=True)
    assert list((root / "deploy" / "compose").glob(".env.bak-*"))


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions only")
def test_env_file_is_owner_only(tmp_path):
    root = _repo(tmp_path)
    generate.write_all(root, _answers(), force=False)
    mode = (root / "deploy" / "compose" / ".env").stat().st_mode
    assert not mode & (stat.S_IRWXG | stat.S_IRWXO)


def test_cli_yes_mode_writes_working_config(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    monkeypatch.setattr(detect, "hardware", lambda *_: detect.Hardware(cpus=8, ram_gb=16, disk_free_gb=100, gpu=None))
    monkeypatch.setattr(detect, "docker_version", lambda: "29.0")
    monkeypatch.setattr(detect, "host_ollama_version", lambda: None)
    monkeypatch.setattr(detect, "docker_volume_exists", lambda _: False)
    monkeypatch.setattr(detect, "docker_mem_gb", lambda: 4.8)
    result = CliRunner().invoke(app, ["init", "--yes", "--no-pull", "--root", str(root)])
    assert result.exit_code == 0, result.output
    env = (root / "deploy" / "compose" / ".env").read_text()
    assert "E2EAI_IMAGE_POSTGRES=pg@sha256:abc" in env
    assert (root / "deploy" / "compose" / "seaweedfs" / "s3.json").exists()
    assert yaml.safe_load((root / "e2eai.yaml").read_text())["tier"] == "lite"


def test_old_host_ollama_is_detected(tmp_path):
    root = _repo(tmp_path)
    (root / "deploy" / "versions.lock").write_text("images:\n  ollama: ollama/ollama:0.35.1@sha256:x\n")
    assert detect.pinned_ollama_version(root) == "0.35.1"
    assert not detect.version_at_least("0.16.1", "0.35.1")
    assert detect.version_at_least("0.35.1", "0.35.1") and detect.version_at_least("1.2", "0.35.1")
