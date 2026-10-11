"""FR-F4 install profiles: core, lab-stage, lab-all, GPU/CPU variants.

PRD §17.2 and §12 define install profiles that select which Docker Compose services run.
This module maps named install profiles to concrete Compose profile names and a small Helm values
boundary. The repo does not ship a Helm chart yet, so the Helm output is intentionally plain data
that a future chart can consume without changing the wizard-facing contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Profile:
    """A named install profile and the Compose services it enables.

    ``compose_profiles`` are Docker Compose profiles (the ``profiles:`` keys in compose.yaml).
    Services in ``always_services`` run in every tier regardless of profile.
    ``gpu_compose_file`` controls whether compose.gpu.yaml is added to COMPOSE_FILE.
    """

    name: str
    description: str
    compose_profiles: frozenset[str] = field(default_factory=frozenset)
    always_services: frozenset[str] = field(default_factory=frozenset)
    gpu_compose_file: bool = False

    def compose_files(self) -> list[str]:
        """Return the ordered Compose file list for this profile/selection."""
        files = ["compose.yaml"]
        if self.gpu_compose_file:
            files.append("compose.gpu.yaml")
        return files


@dataclass(frozen=True)
class InstallSelection(Profile):
    """Resolved install profile variant for Compose and future Helm values."""

    helm_values: dict[str, Any] = field(default_factory=dict)


# The always-on services (PRD T1, compose.yaml services with profile: None).
CORE_SERVICES = frozenset({"postgres", "valkey", "openfga", "seaweedfs", "litellm"})

# Lab stage Compose profiles. Stage names are stable user-facing choices; values are Compose names.
LAB_COMPOSE_PROFILES: dict[str, str] = {
    "eval": "lab-eval",
    "retrieval": "lab-retrieval",
    "serving": "lab-serving",
    "security": "lab-security",
    "connectors": "lab-connectors",
}

MODEL_COMPOSE_PROFILES = frozenset({"ollama", "vllm", "tei-embed", "tei-rerank", "keycloak"})


PROFILES: dict[str, Profile] = {
    "core": Profile(
        name="core",
        description="Minimal infrastructure: Postgres+pgvector, Valkey, OpenFGA, SeaweedFS, LiteLLM.",
        always_services=CORE_SERVICES,
    ),
    "lab-stage": Profile(
        name="lab-stage",
        description="Core plus exactly one selected Lab stage (eval, retrieval, serving, security, connectors).",
        always_services=CORE_SERVICES,
    ),
    "lab-all": Profile(
        name="lab-all",
        description="Core plus every Lab stage enabled at once.",
        compose_profiles=frozenset(LAB_COMPOSE_PROFILES.values()),
        always_services=CORE_SERVICES,
    ),
    "gpu": Profile(
        name="gpu",
        description="GPU variant: adds the GPU device reservation compose file.",
        always_services=CORE_SERVICES,
        gpu_compose_file=True,
    ),
    "cpu": Profile(
        name="cpu",
        description="CPU-only variant: no GPU device reservation.",
        always_services=CORE_SERVICES,
    ),
}


def resolve_profile(name: str) -> Profile:
    """Look up a profile by name, raising ValueError on unknown names."""
    try:
        return PROFILES[name]
    except KeyError:
        raise ValueError(f"unknown install profile: {name!r} (choose from {sorted(PROFILES)})") from None


def resolve_install_selection(
    profile_name: str,
    *,
    lab_stage: str | None = None,
    accelerator: str = "cpu",
    model_profiles: set[str] | frozenset[str] | None = None,
) -> InstallSelection:
    """Resolve an FR-F4 install profile into Compose profiles/files and Helm values.

    ``lab-stage`` requires ``lab_stage`` so it enables one stage at a time. ``lab-all`` enables
    every known Lab stage. ``accelerator='gpu'`` adds ``compose.gpu.yaml``; model-serving profiles
    such as ``ollama`` or ``vllm`` remain explicit because the wizard decides them from selected
    models and tier choices.
    """
    if accelerator not in {"cpu", "gpu"}:
        raise ValueError("accelerator must be 'cpu' or 'gpu'")

    base = resolve_profile(profile_name)
    compose_profiles = set(base.compose_profiles)
    helm_lab: dict[str, Any] = {"mode": "off", "stages": []}

    if profile_name == "lab-stage":
        if lab_stage is None:
            raise ValueError("lab_stage is required when profile_name='lab-stage'")
        try:
            compose_profiles.add(LAB_COMPOSE_PROFILES[lab_stage])
        except KeyError:
            raise ValueError(f"unknown lab_stage: {lab_stage!r} (choose from {sorted(LAB_COMPOSE_PROFILES)})") from None
        helm_lab = {"mode": "stage", "stages": [lab_stage]}
    elif profile_name == "lab-all":
        compose_profiles.update(LAB_COMPOSE_PROFILES.values())
        helm_lab = {"mode": "all", "stages": sorted(LAB_COMPOSE_PROFILES)}

    requested_model_profiles = set(model_profiles or set())
    unknown_model_profiles = requested_model_profiles - MODEL_COMPOSE_PROFILES
    if unknown_model_profiles:
        raise ValueError(f"unknown model compose profiles: {sorted(unknown_model_profiles)}")
    compose_profiles.update(requested_model_profiles)

    gpu = accelerator == "gpu"
    helm_values = {
        "profile": profile_name,
        "accelerator": accelerator,
        "core": {"enabled": True, "services": sorted(CORE_SERVICES)},
        "lab": helm_lab,
        "composeProfiles": sorted(compose_profiles),
    }
    return InstallSelection(
        name=profile_name,
        description=base.description,
        compose_profiles=frozenset(compose_profiles),
        always_services=CORE_SERVICES,
        gpu_compose_file=gpu,
        helm_values=helm_values,
    )
