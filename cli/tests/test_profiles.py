"""FR-F4 Install profiles: core, lab-stage, lab-all, GPU/CPU variants for compose.

Tests cover:
  * Profile definitions match the PRD §17.2 / §12 install profiles
  * Each profile maps to a concrete set of compose service profiles
  * Profile validation rejects unknown profiles
  * GPU variant adds the gpu device reservation compose file
  * core profile is the minimal always-installed set
  * Lab-stage enables one Lab stage at a time; lab-all enables all stages
"""
import pytest

from e2eai_wizard import profiles


def test_core_profile_has_always_installed_services():
    p = profiles.PROFILES["core"]
    assert p.compose_profiles == set()  # core = always-on, no optional profiles
    assert p.gpu_compose_file is False
    assert p.description


def test_lab_stage_resolves_one_requested_stage():
    selection = profiles.resolve_install_selection("lab-stage", lab_stage="eval")
    assert selection.compose_profiles == frozenset({"lab-eval"})
    assert selection.helm_values["lab"]["stages"] == ["eval"]


def test_lab_stage_requires_stage_name():
    with pytest.raises(ValueError, match="lab_stage"):
        profiles.resolve_install_selection("lab-stage")


def test_lab_all_profile_enables_all_lab_stages():
    selection = profiles.resolve_install_selection("lab-all")
    assert selection.compose_profiles == frozenset(profiles.LAB_COMPOSE_PROFILES.values())
    assert selection.helm_values["lab"]["mode"] == "all"


def test_profiles_contain_core_lab_stage_lab_all():
    names = set(profiles.PROFILES)
    assert {"core", "lab-stage", "lab-all"} <= names


def test_gpu_variant_adds_gpu_compose_file():
    gpu = profiles.resolve_install_selection("core", accelerator="gpu", model_profiles={"ollama", "vllm"})
    assert gpu.gpu_compose_file is True
    assert gpu.compose_profiles == frozenset({"ollama", "vllm"})
    assert gpu.compose_files() == ["compose.yaml", "compose.gpu.yaml"]
    assert gpu.helm_values["accelerator"] == "gpu"


def test_cpu_variant_does_not_use_gpu_compose_file():
    cpu = profiles.resolve_install_selection("core", accelerator="cpu")
    assert cpu.gpu_compose_file is False
    assert cpu.helm_values["accelerator"] == "cpu"


def test_resolve_profile_existing():
    p = profiles.resolve_profile("core")
    assert p is profiles.PROFILES["core"]


def test_resolve_profile_unknown_raises():
    with pytest.raises(ValueError, match="unknown"):
        profiles.resolve_profile("nonexistent")


def test_profile_services_returns_enabled_services():
    p = profiles.PROFILES["core"]
    # core always includes the base infra services
    assert "postgres" in p.always_services
    assert "valkey" in p.always_services
    assert "openfga" in p.always_services
    assert "seaweedfs" in p.always_services
    assert "litellm" in p.always_services


def test_profile_compose_file_list_includes_compose_yaml():
    p = profiles.resolve_install_selection("core", accelerator="gpu")
    files = p.compose_files()
    assert "compose.yaml" in files
    assert "compose.gpu.yaml" in files


def test_profile_compose_file_list_cpu_no_gpu():
    p = profiles.resolve_install_selection("core", accelerator="cpu")
    files = p.compose_files()
    assert "compose.yaml" in files
    assert "compose.gpu.yaml" not in files
