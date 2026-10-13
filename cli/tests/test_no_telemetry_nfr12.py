"""NFR-12: no outbound telemetry or update checks by default."""

from pathlib import Path

import yaml

from e2eai_wizard import generate

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = yaml.safe_load((ROOT / "deploy" / "compose" / "compose.yaml").read_text(encoding="utf-8"))


def _env(service: str) -> dict:
    env = COMPOSE["services"][service].get("environment") or {}
    if isinstance(env, list):
        env = dict(item.split("=", 1) for item in env)
    return {k: str(v) for k, v in env.items()}


def test_litellm_config_disables_telemetry():
    from e2eai_wizard.services import SERVICES

    catalog = generate.load_catalog(ROOT)
    a = generate.default_answers(
        tier="lite", ports={s.name: s.default_port for s in SERVICES}, host_ollama=False, gpu=False)
    a["models"] = {r: [] for r in generate.ROLES} | {"external": []}
    a["models"]["chat"] = ["qwen3:1.7b"]
    a["models"]["embedding"] = ["bge-m3"]
    cfg = yaml.safe_load(generate.render_litellm_config(a, catalog))
    assert cfg["litellm_settings"]["telemetry"] is False


def test_vllm_has_usage_stats_and_hf_telemetry_off():
    env = _env("vllm")
    assert env["VLLM_NO_USAGE_STATS"] == "1"
    assert env["DO_NOT_TRACK"] == "1"
    assert env["HF_HUB_DISABLE_TELEMETRY"] == "1"


def test_tei_services_have_hf_telemetry_off():
    for svc in ("tei-embed", "tei-rerank"):
        assert _env(svc)["HF_HUB_DISABLE_TELEMETRY"] == "1", svc


def test_ollama_service_runs_local_only_without_cloud_features():
    # OLLAMA_NO_CLOUD exists since Ollama v0.16.2; the pinned image is newer (deploy/versions.lock).
    assert _env("ollama")["OLLAMA_NO_CLOUD"] == "1"


def test_openfga_tracing_is_explicitly_off_so_no_traces_leave_the_host():
    for svc in ("openfga", "openfga-migrate"):
        assert _env(svc)["OPENFGA_TRACE_ENABLED"] == "false", svc


def test_every_service_that_publishes_a_port_binds_to_the_configured_address_only():
    for name, svc in COMPOSE["services"].items():
        for port in svc.get("ports") or []:
            assert str(port).startswith("${BIND_ADDRESS}:"), f"{name} publishes {port} on all interfaces"
