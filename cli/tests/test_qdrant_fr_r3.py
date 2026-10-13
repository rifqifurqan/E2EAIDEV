"""FR-R3: Qdrant as the optional P1 vector store (pinned image, private key, no telemetry, wizard choice)."""

from pathlib import Path

import yaml

from e2eai_wizard import generate
from e2eai_wizard.licenses import TOOL_LICENSES
from e2eai_wizard.services import BY_NAME, SERVICES, enabled_services

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = yaml.safe_load((ROOT / "deploy" / "compose" / "compose.yaml").read_text(encoding="utf-8"))
LOCK = yaml.safe_load((ROOT / "deploy" / "versions.lock").read_text(encoding="utf-8"))


def _answers(qdrant: bool) -> dict:
    a = generate.default_answers(tier="lite", ports={s.name: s.default_port for s in SERVICES},
                                 host_ollama=True, gpu=False)
    a["optional"]["qdrant"] = qdrant
    return a


def test_qdrant_image_is_pinned_by_digest():
    image = LOCK["images"]["qdrant"]
    assert image.startswith("qdrant/qdrant:v") and "@sha256:" in image


def test_qdrant_is_an_optional_profile_service_on_a_1xxxx_port_with_a_license_entry():
    assert BY_NAME["qdrant"].profile == "qdrant" and BY_NAME["qdrant"].default_port == 16333
    assert TOOL_LICENSES["qdrant"].spdx == "Apache-2.0"
    assert "qdrant" not in enabled_services(_answers(False))
    assert "qdrant" in enabled_services(_answers(True))


def test_compose_service_requires_key_disables_telemetry_and_binds_to_bind_address():
    svc = COMPOSE["services"]["qdrant"]
    assert svc["profiles"] == ["qdrant"] and "E2EAI_IMAGE_QDRANT" in svc["image"]
    env = svc["environment"]
    assert env["QDRANT__SERVICE__API_KEY"] == "${QDRANT_API_KEY}"
    assert str(env["QDRANT__TELEMETRY_DISABLED"]).lower() == "true"  # NFR-12
    assert all(str(p).startswith("${BIND_ADDRESS}:${QDRANT_PORT}") for p in svc["ports"])
    assert any("qdrantdata" in str(v) for v in svc["volumes"]) and "qdrantdata" in COMPOSE["volumes"]


def test_wizard_selecting_qdrant_switches_vector_store_and_writes_url_and_key():
    off = yaml.safe_load(generate.render_config(_answers(False)))
    assert off["components"]["vector_store"] == "pgvector" and "qdrant" not in off

    a = _answers(True)
    cfg = yaml.safe_load(generate.render_config(a))
    assert cfg["components"]["vector_store"] == "qdrant"
    assert cfg["qdrant"]["url"] == "http://127.0.0.1:16333"
    assert "QDRANT_API_KEY=" in generate.render_env(a, LOCK["images"])
    assert "QDRANT_API_KEY" not in yaml.safe_dump(cfg).replace("env:QDRANT_API_KEY", "")  # config holds a ref only
    assert len(a["secrets"]["QDRANT_API_KEY"]) >= 16 and generate.validate_secret(a["secrets"]["QDRANT_API_KEY"]) is None


def test_load_answers_round_trips_the_qdrant_choice(tmp_path):
    a = _answers(True)
    (tmp_path / "deploy" / "compose").mkdir(parents=True)
    (tmp_path / "deploy" / "compose" / ".env").write_text(generate.render_env(a, LOCK["images"]), encoding="utf-8")
    a["models"] = {r: [] for r in generate.ROLES} | {"external": []}
    (tmp_path / "e2eai.yaml").write_text(generate.render_config(a), encoding="utf-8")
    assert generate.load_answers(tmp_path)["optional"]["qdrant"] is True
