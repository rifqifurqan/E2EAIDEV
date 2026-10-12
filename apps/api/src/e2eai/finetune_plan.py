"""Fine-tuning and distillation planning with results fed back into benchmarking (FR-M6).

Deterministic/offline planning layer. It validates a job spec (LoRA / QLoRA / full / DPO / distillation),
estimates GPU memory, checks training examples (approved label sources, no PII, no empty fields), renders
a trainer-neutral config (Unsloth / Axolotl / TRL are adapters behind it), and converts a finished run's
measurements into FR-T11 benchmark combinations for a before/after comparison. No training runs here.
Issue reports carry example indexes and codes only: never example text.
"""

from __future__ import annotations

import math
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .auth import current_session, require_scope
from .core.errors import AppError
from .pii import select_detector

METHODS = {"lora", "qlora", "full", "dpo", "distillation"}
TRAINERS = ["unsloth", "axolotl", "trl"]
APPROVED_LABEL_SOURCES = {"gold", "human", "synthetic_reviewed", "feedback_accepted"}
SFT_KINDS = {"fine_tuning", "gold"}
MAX_EXAMPLES_CHECKED = 5000
SMALL_DATASET = 100


def _num(value: Any, name: str, lo: float, hi: float, *, integer: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    if integer and int(value) != value:
        raise ValueError(f"{name} must be an integer")
    if not lo <= value <= hi:
        raise ValueError(f"{name} out of range")
    return value


def estimate_training_memory_gb(*, method: str, params_b: float, batch_size: int, max_seq_len: int, rank: int) -> float:
    """Rough GPU memory: weights (+ optimizer for full), small adapter state, activations."""
    if method == "full":
        weights = params_b * 16.0  # fp16 weights + grads + Adam states + fp32 master copy
    elif method == "qlora":
        weights = params_b * 0.5 * 1.1
    else:
        weights = params_b * 2.0 * 1.1
    adapters = 0.0 if method == "full" else params_b * rank / 4096.0 * 0.4
    activations = 0.5 + batch_size * max_seq_len / 2048.0 * 0.5
    total = weights + adapters + activations
    if method == "dpo":
        total *= 1.2  # reference-model forward pass
    return round(total, 2)


def build_plan(spec: dict[str, Any], *, gpu_memory_gb: float | None = None) -> dict[str, Any]:
    method = spec.get("method")
    if method not in METHODS:
        raise ValueError("unsupported method")
    base_model = spec.get("base_model")
    if not isinstance(base_model, str) or not base_model.strip():
        raise ValueError("base_model is required")
    params_b = _num(spec.get("params_b"), "params_b", 0.001, 2000)
    ds = spec.get("dataset") or {}
    if not isinstance(ds, dict) or not ds.get("id"):
        raise ValueError("dataset id is required")
    kind = ds.get("kind")
    examples = int(_num(ds.get("examples"), "examples", 1, 100_000_000, integer=True))
    if method == "dpo":
        if kind != "preference":
            raise ValueError("dpo needs a preference dataset")
    elif kind not in SFT_KINDS:
        raise ValueError("dataset kind is not usable for training")
    teacher = spec.get("teacher_model")
    if method == "distillation" and (not isinstance(teacher, str) or not teacher.strip()):
        raise ValueError("distillation needs a teacher_model")

    h = spec.get("hyperparameters") or {}
    rank = int(_num(h.get("rank", 16), "rank", 1, 256, integer=True))
    alpha = int(_num(h.get("alpha", rank * 2), "alpha", 1, 1024, integer=True))
    lr = float(_num(h.get("learning_rate"), "learning_rate", 1e-9, 1e-2))
    epochs = int(_num(h.get("epochs"), "epochs", 1, 50, integer=True))
    batch = int(_num(h.get("batch_size"), "batch_size", 1, 512, integer=True))
    seq = int(_num(h.get("max_seq_len", 2048), "max_seq_len", 128, 32768, integer=True))

    steps_per_epoch = math.ceil(examples / batch)
    memory = estimate_training_memory_gb(method=method, params_b=params_b, batch_size=batch, max_seq_len=seq, rank=rank)
    config: dict[str, Any] = {
        "base_model": base_model,
        "dataset": {"id": str(ds["id"]), "version": ds.get("version")},
        "training": {"learning_rate": lr, "epochs": epochs, "batch_size": batch, "max_seq_len": seq},
    }
    if method != "full":
        config["lora"] = {"r": rank, "alpha": alpha}
    if method == "dpo":
        config["dpo"] = {"beta": float(h.get("beta", 0.1))}
    if method == "distillation":
        config["distillation"] = {"teacher": teacher}

    warnings = []
    if examples < SMALL_DATASET:
        warnings.append("dataset_small")
    fits: bool | None = None
    if gpu_memory_gb is not None:
        fits = memory <= gpu_memory_gb
        if not fits:
            warnings.append("exceeds_gpu_memory")
    return {
        "method": method,
        "quantization_bits": 4 if method == "qlora" else 16,
        "estimated_gpu_memory_gb": memory,
        "fits_gpu": fits,
        "steps_per_epoch": steps_per_epoch,
        "total_steps": steps_per_epoch * epochs,
        "supported_trainers": list(TRAINERS),
        "trainer_config": config,
        "warnings": warnings,
    }


def check_training_examples(examples: list[dict[str, Any]]) -> dict[str, Any]:
    detector = select_detector()
    issues: list[dict[str, Any]] = []
    for i, ex in enumerate(examples[:MAX_EXAMPLES_CHECKED]):
        text_fields = ("prompt", "response", "chosen", "rejected")
        if "chosen" in ex:
            required = ("prompt", "chosen", "rejected")
        else:
            required = ("prompt", "response")
        if any(not isinstance(ex.get(f), str) or not ex[f].strip() for f in required):
            issues.append({"index": i, "code": "empty_field"})
            continue
        if ex.get("label_source") not in APPROVED_LABEL_SOURCES:
            issues.append({"index": i, "code": "label_source_not_approved"})
        if any(isinstance(ex.get(f), str) and detector.detect(ex[f]) for f in text_fields):
            issues.append({"index": i, "code": "pii_detected"})
    return {"ok": not issues, "checked": min(len(examples), MAX_EXAMPLES_CHECKED), "issues": issues}


def results_to_benchmark(run: dict[str, Any], *, prompt: str, dataset: str) -> dict[str, Any]:
    base, tuned = run.get("base_model"), run.get("tuned_model")
    base_s, tuned_s = run.get("base_samples") or [], run.get("tuned_samples") or []
    if not base or not tuned or not base_s or not tuned_s:
        raise ValueError("base and tuned models with samples are required")

    def mean_quality(samples: list[dict[str, Any]]) -> float:
        return sum(float(s.get("quality", 0.0) or 0.0) for s in samples) / len(samples)

    combos = [
        {"model": base, "prompt": prompt, "dataset": dataset, "samples": base_s},
        {"model": tuned, "prompt": prompt, "dataset": dataset, "samples": tuned_s},
    ]
    return {"combinations": combos, "quality_delta": round(mean_quality(tuned_s) - mean_quality(base_s), 4)}


class DatasetIn(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    version: int | None = None
    kind: str = Field(max_length=30)
    examples: int


class FinetunePlanIn(BaseModel):
    method: str = Field(max_length=20)
    base_model: str = Field(max_length=200)
    params_b: float
    teacher_model: str | None = Field(default=None, max_length=200)
    dataset: DatasetIn
    hyperparameters: dict[str, Any] = {}
    gpu_memory_gb: float | None = Field(default=None, gt=0)


class CheckDataIn(BaseModel):
    examples: list[dict[str, Any]] = Field(max_length=MAX_EXAMPLES_CHECKED)


class ResultsIn(BaseModel):
    base_model: str = Field(max_length=200)
    tuned_model: str = Field(max_length=200)
    base_samples: list[dict[str, Any]] = Field(max_length=10_000)
    tuned_samples: list[dict[str, Any]] = Field(max_length=10_000)
    prompt: str = Field(max_length=200)
    dataset: str = Field(max_length=200)


router = APIRouter(prefix="/api/v1/models/finetune", tags=["models"])


@router.post("/plan")
async def plan_api(body: FinetunePlanIn, sess: dict = Depends(current_session)) -> dict[str, Any]:
    """FR-M6: validate a fine-tuning/distillation job spec and return a trainer-neutral plan."""
    require_scope(sess, "evals")
    spec = body.model_dump(exclude={"gpu_memory_gb"})
    try:
        return build_plan(spec, gpu_memory_gb=body.gpu_memory_gb)
    except ValueError as exc:
        raise AppError(400, str(exc)) from exc


@router.post("/check-data")
async def check_data_api(body: CheckDataIn, sess: dict = Depends(current_session)) -> dict[str, Any]:
    """FR-M6: check training examples (indexes and codes only are returned)."""
    require_scope(sess, "evals")
    return check_training_examples(body.examples)


@router.post("/results")
async def results_api(body: ResultsIn, sess: dict = Depends(current_session)) -> dict[str, Any]:
    """FR-M6: turn a finished run's samples into benchmark combinations for before/after comparison."""
    require_scope(sess, "evals")
    from .benchmark import summarize_combination

    try:
        out = results_to_benchmark(body.model_dump(exclude={"prompt", "dataset"}), prompt=body.prompt, dataset=body.dataset)
    except ValueError as exc:
        raise AppError(400, str(exc)) from exc
    return {"quality_delta": out["quality_delta"], "leaderboard": [summarize_combination(c) for c in out["combinations"]]}
