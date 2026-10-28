"""PRD T1: Caddy is the single HTTPS front door (local CA on Lite). Optional profile, pinned, private admin API."""

from pathlib import Path

import yaml

from e2eai_wizard import generate
from e2eai_wizard.licenses import TOOL_LICENSES
from e2eai_wizard.services import BY_NAME, SERVICES, enabled_services

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = yaml.safe_load((ROOT / "deploy" / "compose" / "compose.yaml").read_text(encoding="utf-8"))
LOCK = yaml.safe_load((ROOT / "deploy" / "versions.lock").read_text(encoding="utf-8"))
CADDYFILE = ROOT / "deploy" / "compose" / "caddy" / "Caddyfile"


def _answers(caddy: bool) -> dict:
    a = generate.default_answers(tier="lite", ports={s.name: s.default_port for s in SERVICES},
                                 host_ollama=True, gpu=False)
    a["optional"]["caddy"] = caddy
    return a


def test_caddy_image_is_pinned_by_digest():
    image = LOCK["images"]["caddy"]
    assert image.startswith("caddy:2.") and image.split("@")[0].endswith("-alpine") and "@sha256:" in image


def test_caddy_is_an_optional_profile_service_with_a_license_entry():
    assert BY_NAME["caddy"].profile == "caddy" and BY_NAME["caddy"].default_port == 18443
    assert TOOL_LICENSES["caddy"].spdx == "Apache-2.0"
    assert "caddy" not in enabled_services(_answers(False))
    assert "caddy" in enabled_services(_answers(True))


def test_compose_service_is_private_by_default_and_mounts_the_caddyfile_read_only():
    svc = COMPOSE["services"]["caddy"]
    assert svc["profiles"] == ["caddy"] and "E2EAI_IMAGE_CADDY" in svc["image"]
    assert all(str(p).startswith("${BIND_ADDRESS}:${CADDY_PORT}:") for p in svc["ports"])
    assert any(str(v).endswith("/etc/caddy/Caddyfile:ro") for v in svc["volumes"])
    assert "host.docker.internal:host-gateway" in svc["extra_hosts"]  # web/API run on the host in development
    assert svc["environment"]["WEB_UPSTREAM"] == "${WEB_UPSTREAM}"
    assert "caddydata" in COMPOSE["volumes"] and "caddyconfig" in COMPOSE["volumes"]


def test_caddyfile_has_tls_hsts_no_admin_api_and_one_web_upstream():
    text = CADDYFILE.read_text(encoding="utf-8")
    assert "admin off" in text                      # no unauthenticated config endpoint
    assert "tls internal" in text                   # local CA on Lite
    assert "Strict-Transport-Security" in text
    assert "reverse_proxy {$WEB_UPSTREAM}" in text  # API stays private behind the web proxy
    assert "-Server" in text                        # do not advertise the server software


def test_wizard_writes_profile_and_upstream_to_env_and_round_trips(tmp_path):
    a = _answers(True)
    env = generate.render_env(a, LOCK["images"])
    assert "COMPOSE_PROFILES=caddy" in env and "CADDY_PORT=18443" in env
    assert "WEB_UPSTREAM=host.docker.internal:13000" in env
    assert "E2EAI_IMAGE_CADDY=caddy:2." in env
    assert "caddy" in yaml.safe_load(generate.render_config(a))["services"]

    (tmp_path / "deploy" / "compose").mkdir(parents=True)
    (tmp_path / "deploy" / "compose" / ".env").write_text(env, encoding="utf-8")
    (tmp_path / "e2eai.yaml").write_text(generate.render_config(a), encoding="utf-8")
    assert generate.load_answers(tmp_path)["optional"]["caddy"] is True


def test_caddyfile_names_its_sites_so_a_certificate_can_be_issued():
    """Found live: `https://:8443` (no host) got no certificate, so every TLS handshake failed."""
    text = CADDYFILE.read_text(encoding="utf-8")
    assert "https://localhost:8443" in text and "https://127.0.0.1:8443" in text
    assert "https://:8443" not in text
