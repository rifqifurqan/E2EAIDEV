from pathlib import Path

import yaml
from typer.testing import CliRunner

from e2eai_wizard import detect, generate, models
from e2eai_wizard.cli import app

ROOT = Path(__file__).resolve().parents[2]
CATALOG = models.load_catalog(ROOT)
PC = models.Machine(ram_gb=22, gpu_vram_gb=6, docker_mem_gb=4.8, ollama_in_docker=True)  # the owner's laptop
PC_HOST_OLLAMA = models.Machine(ram_gb=22, gpu_vram_gb=6, docker_mem_gb=4.8, ollama_in_docker=False)


def test_catalog_entries_are_valid_and_unique():
    ids = [m.id for m in CATALOG.values()]
    assert len(ids) == len(set(ids))
    for m in CATALOG.values():
        assert m.role in models.ROLES and m.served_by in ("ollama", "tei", "vllm")
        assert m.license_class in ("permissive", "restrictive", "non-commercial")
        assert m.mem_gb > 0


def test_fit_uses_gpu_then_cpu_then_rejects():
    small, big = CATALOG["qwen3:4b"], CATALOG["qwen3:14b"]
    assert models.fit(small, PC) == "gpu"
    assert models.fit(CATALOG["qwen3:8b"], PC_HOST_OLLAMA) == "cpu"  # 6.3 GB > 6 GB VRAM, fits host RAM
    assert models.fit(CATALOG["qwen3:8b"], PC) == "too_big"  # in the container it must fit Docker's 4.8 GB
    assert models.fit(big, models.Machine(ram_gb=16, gpu_vram_gb=0, docker_mem_gb=4.8)) == "too_big"


def test_vllm_models_require_gpu_vram_and_do_not_fall_back_to_cpu():
    vllm = CATALOG["qwen3-8b-vllm"]
    assert models.fit(vllm, models.Machine(ram_gb=128, gpu_vram_gb=24, docker_mem_gb=16)) == "gpu"
    assert models.fit(vllm, models.Machine(ram_gb=128, gpu_vram_gb=0, docker_mem_gb=16)) == "too_big"
    assert models.fit(vllm, models.Machine(ram_gb=128, gpu_vram_gb=8, docker_mem_gb=16)) == "too_big"


def test_tei_models_must_fit_docker_memory_together():
    rerank, emb = CATALOG["bge-reranker-v2-m3"], CATALOG["bge-m3-tei"]
    assert models.fit(rerank, PC_HOST_OLLAMA) == "cpu"
    assert models.fit(rerank, PC_HOST_OLLAMA, tei_used_gb=emb.mem_gb) == "too_big"


def test_ollama_container_memory_counts_against_docker():
    # Regression 2026-10-05: bge-reranker-v2-m3 restart-looped next to the Ollama container in 4.8 GB.
    assert models.fit(CATALOG["bge-reranker-v2-m3"], PC) == "too_big"
    assert models.fit(CATALOG["gte-multilingual-reranker-base"], PC) == "cpu"


def test_license_warnings():
    assert models.license_warning(CATALOG["qwen3:4b"]) is None
    assert "conditions" in models.license_warning(CATALOG["llama3.2:3b"])
    nc = models.Model(id="x", role="chat", served_by="ollama", source="x", size_gb=1, mem_gb=1,
                      license="cc-by-nc-4.0", license_class="non-commercial", languages="")
    assert "NON-COMMERCIAL" in models.license_warning(nc)


def test_recommendations_for_the_owners_laptop():
    rec = models.recommend_all(CATALOG, PC)
    assert rec["chat"] == ["qwen3.5:4b"]          # largest permissive model inside 6 GB VRAM
    assert rec["embedding"] == ["bge-m3"]         # TEI embedding doesn't fit 4.8 GB; bge-m3 on Ollama/GPU
    assert rec["reranker"] == []                  # reranker "none" on Lite CPU (FR-R2); see recommend_all
    assert rec["vision"] == [] and rec["safety"] == []


def test_litellm_config_routes_each_model_and_holds_no_secrets():
    a = generate.default_answers(tier="lite", ports={}, host_ollama=True, gpu=False)
    a["api_keys"] = {"OPENAI_API_KEY": "«redacted:sk-…»"}
    models.apply_selection(a, {"chat": ["qwen3:4b"], "embedding": ["bge-m3-tei"], "reranker": [],
                               "vision": [], "safety": [],
                               "external": [{"provider": "openai", "model": "gpt-5-mini"}]}, CATALOG)
    text = generate.render_litellm_config(a, CATALOG)
    cfg = yaml.safe_load(text)
    by_name = {m["model_name"]: m["litellm_params"] for m in cfg["model_list"]}
    assert by_name["qwen3:4b"] == {"model": "ollama_chat/qwen3:4b", "api_base": "os.environ/OLLAMA_BASE_URL"}
    assert by_name["bge-m3-tei"]["model"] == "openai/BAAI/bge-m3"
    assert by_name["bge-m3-tei"]["api_base"] == "http://tei-embed:80/v1"
    assert by_name["openai/gpt-5-mini"]["api_key"] == "os.environ/OPENAI_API_KEY"
    assert "«redacted:sk-…»" not in text
    assert a["optional"]["tei-embed"] and a["tei_models"]["tei-embed"] == "BAAI/bge-m3"


def test_vllm_selection_enables_gpu_profile_and_litellm_openai_route():
    a = generate.default_answers(tier="standard", ports={}, host_ollama=True, gpu=True)
    models.apply_selection(a, {"chat": ["qwen3-8b-vllm"], "embedding": [], "reranker": [],
                               "vision": [], "safety": [], "external": []}, CATALOG)

    env = generate.render_env(a, images={"vllm": "vllm/vllm-openai:v0.11.0@sha256:test"})
    assert "COMPOSE_PROFILES=vllm" in env
    assert "compose.gpu.yaml" in env
    assert "VLLM_MODEL=Qwen/Qwen3-8B" in env

    cfg = yaml.safe_load(generate.render_litellm_config(a, CATALOG))
    by_name = {m["model_name"]: m["litellm_params"] for m in cfg["model_list"]}
    assert by_name["qwen3-8b-vllm"] == {
        "model": "openai/Qwen/Qwen3-8B",
        "api_base": "http://vllm:8000/v1",
        "api_key": "os.environ/VLLM_API_KEY",
    }
    assert a["optional"]["vllm"] is True and a["vllm_model"] == "Qwen/Qwen3-8B"


def _repo(tmp_path):
    (tmp_path / "deploy" / "compose" / "seaweedfs").mkdir(parents=True)
    (tmp_path / "deploy" / "versions.lock").write_text("images:\n  postgres: pg@sha256:abc\n")
    (tmp_path / "catalog").mkdir()
    (tmp_path / "catalog" / "models.yaml").write_text((ROOT / "catalog" / "models.yaml").read_text())
    return tmp_path


def _fake_machine(monkeypatch):
    monkeypatch.setattr(detect, "hardware", lambda *_: detect.Hardware(cpus=16, ram_gb=22, disk_free_gb=100, gpu=detect.Gpu("RTX", 6)))
    monkeypatch.setattr(detect, "docker_version", lambda: "29.0")
    monkeypatch.setattr(detect, "docker_mem_gb", lambda: 4.8)
    monkeypatch.setattr(detect, "host_ollama_version", lambda: "0.16.3")
    monkeypatch.setattr(detect, "docker_volume_exists", lambda _: False)


def test_init_then_models_keeps_passwords_and_updates_models(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    _fake_machine(monkeypatch)
    r = CliRunner().invoke(app, ["init", "--yes", "--no-pull", "--root", str(root)])
    assert r.exit_code == 0, r.output
    env1 = generate.read_env(root / "deploy" / "compose" / ".env")
    assert yaml.safe_load((root / "e2eai.yaml").read_text())["models"]["chat"] == ["qwen3.5:4b"]
    assert (root / "deploy" / "compose" / "litellm" / "config.yaml").exists()

    r = CliRunner().invoke(app, ["models", "--root", str(root), "--no-pull"], input="4\n2\n0\n0\n0\nn\n")
    assert r.exit_code == 0, r.output
    env2 = generate.read_env(root / "deploy" / "compose" / ".env")
    assert env2["POSTGRES_PASSWORD"] == env1["POSTGRES_PASSWORD"]
    assert env2["TEI_EMBED_MODEL"] == "BAAI/bge-m3" and env2["TEI_RERANK_MODEL"] == ""
    cfg = yaml.safe_load((root / "e2eai.yaml").read_text())
    assert cfg["models"]["chat"] == ["qwen3:4b"] and cfg["models"]["embedding"] == ["bge-m3-tei"]
