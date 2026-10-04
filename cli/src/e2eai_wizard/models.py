"""Model catalog, hardware fit, license gate and recommendations (FR-F5a, FR-F5b)."""

from dataclasses import dataclass
from pathlib import Path

import yaml

ROLES = ("chat", "embedding", "reranker", "vision", "safety")
MULTI = {"chat", "vision", "safety"}  # roles where several models can be installed for Lab comparison
STACK_GB = 1.5        # Docker headroom for the infra stack (measured 0.87 GiB idle)
CPU_RESERVE_GB = 6.0  # RAM kept free for the OS and the platform when a model runs on CPU
CPU_COMFORT_GB = 4.5  # largest model recommended for CPU-only inference (PRD §12: <= 4B on CPU)

EXTERNAL_PROVIDERS = {  # provider -> (LiteLLM prefix, env var for the key)
    "openai": ("openai", "OPENAI_API_KEY"),
    "anthropic": ("anthropic", "ANTHROPIC_API_KEY"),
    "gemini": ("gemini", "GEMINI_API_KEY"),
}


@dataclass(frozen=True)
class Model:
    id: str
    role: str
    served_by: str
    source: str
    size_gb: float
    mem_gb: float
    license: str
    license_class: str
    languages: str
    dim: int | None = None


@dataclass(frozen=True)
class Machine:
    ram_gb: float
    gpu_vram_gb: float  # GPU available to Ollama (0 = none)
    docker_mem_gb: float


def load_catalog(root: Path) -> dict[str, Model]:
    rows = yaml.safe_load((root / "catalog" / "models.yaml").read_text(encoding="utf-8"))["models"]
    return {r["id"]: Model(**r) for r in rows}


def fit(m: Model, machine: Machine, tei_used_gb: float = 0.0) -> str:
    """'gpu', 'cpu', or 'too_big'. TEI runs inside Docker, so it must fit Docker's memory limit."""
    if m.served_by == "tei":
        return "cpu" if m.mem_gb + tei_used_gb + STACK_GB <= machine.docker_mem_gb else "too_big"
    if m.mem_gb <= machine.gpu_vram_gb:
        return "gpu"
    return "cpu" if m.mem_gb <= machine.ram_gb - CPU_RESERVE_GB else "too_big"


def license_warning(m: Model) -> str | None:
    if m.license_class == "non-commercial":
        return f"NON-COMMERCIAL license ({m.license}): not allowed for company use"
    if m.license_class == "restrictive":
        return f"{m.license} license has conditions; review it before company use"
    return None


def _pick(candidates: list[Model], machine: Machine, tei_used_gb: float) -> Model | None:
    ok = [m for m in candidates if m.license_class == "permissive"]
    gpu = [m for m in ok if fit(m, machine, tei_used_gb) == "gpu"]
    cpu = [m for m in ok if fit(m, machine, tei_used_gb) == "cpu" and m.mem_gb <= CPU_COMFORT_GB]
    pool = gpu or cpu
    return max(pool, key=lambda m: m.size_gb) if pool else None


def recommend_all(catalog: dict[str, Model], machine: Machine) -> dict[str, list[str]]:
    """Hardware-based suggestion only; the user decides. Vision and safety are opt-in add-ons."""
    by_role = {r: [m for m in catalog.values() if m.role == r] for r in ROLES}
    chat = _pick(by_role["chat"], machine, 0)
    # Embedding + reranker must share Docker memory when both run on TEI: try the pair first.
    rerank = _pick(by_role["reranker"], machine, 0)
    used = rerank.mem_gb if rerank else 0.0
    emb = _pick([m for m in by_role["embedding"] if m.served_by == "tei"], machine, used) or _pick(
        [m for m in by_role["embedding"] if m.served_by == "ollama"], machine, used)
    return {
        "chat": [chat.id] if chat else [],
        "embedding": [emb.id] if emb else [],
        "reranker": [rerank.id] if rerank else [],
        "vision": [],
        "safety": [],
    }


def apply_selection(a: dict, selection: dict, catalog: dict[str, Model]) -> None:
    """Store the choice in the answers and switch the TEI/Ollama services it needs."""
    a["models"] = {r: list(selection.get(r, [])) for r in ROLES} | {"external": list(selection.get("external", []))}
    chosen = [catalog[i] for r in ROLES for i in a["models"][r]]
    tei_emb = next((m for m in chosen if m.role == "embedding" and m.served_by == "tei"), None)
    rerank = next((m for m in chosen if m.role == "reranker"), None)
    a["tei_models"] = {"tei-embed": tei_emb.source if tei_emb else "", "tei-rerank": rerank.source if rerank else ""}
    a["optional"]["tei-embed"] = bool(tei_emb)
    a["optional"]["tei-rerank"] = bool(rerank)
    if not a["host_ollama"] and any(m.served_by == "ollama" for m in chosen):
        a["optional"]["ollama"] = True
    a["egress_external"] = bool(a["models"]["external"])
