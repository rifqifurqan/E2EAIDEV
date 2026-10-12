"""Quantization lab: compare AWQ / GPTQ / GGUF variants on quality loss, speed, and memory (FR-M5).

Deterministic/offline: quality and speed are supplied by the caller (measured by the benchmark runner);
memory is taken from the caller when measured, else estimated from parameter count and bit width.
Output carries variant ids, formats, and numbers only. Pickle-based formats are not accepted here
(see FR-M8 for model file security).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .auth import current_session, require_scope
from .core.errors import AppError

# Serving engines able to load each format (what the platform's serving interface can route to).
_FORMAT_ENGINES: dict[str, list[str]] = {
    "fp16": ["vllm", "transformers"],
    "awq": ["vllm", "transformers"],
    "gptq": ["vllm", "transformers"],
    "gguf": ["ollama", "llamacpp"],
}
_ALLOWED_BITS = {2, 3, 4, 5, 6, 8, 16}
_OVERHEAD = 1.1  # KV cache / activations / runtime overhead on top of raw weights
MAX_VARIANTS = 50


def compatible_engines(fmt: str) -> list[str]:
    if fmt not in _FORMAT_ENGINES:
        raise ValueError("unsupported quantization format")
    return list(_FORMAT_ENGINES[fmt])


def estimate_memory_gb(*, params_b: float, bits: int) -> float:
    if not isinstance(params_b, (int, float)) or params_b <= 0:
        raise ValueError("params_b must be positive")
    if bits not in _ALLOWED_BITS or isinstance(bits, bool) or int(bits) != bits:
        raise ValueError("unsupported bit width")
    return round(params_b * bits / 8.0 * _OVERHEAD, 3)


def compare_variants(variants: list[dict[str, Any]], *, baseline_id: str, params_b: float) -> dict[str, Any]:
    if not variants or len(variants) > MAX_VARIANTS:
        raise ValueError("provide between 1 and 50 variants")
    seen: set[str] = set()
    prepared: dict[str, dict[str, Any]] = {}
    for v in variants:
        vid = v.get("id")
        if not isinstance(vid, str) or not vid.strip():
            raise ValueError("variant needs an id")
        if vid in seen:
            raise ValueError("duplicate variant id")
        seen.add(vid)
        fmt = v.get("format")
        engines = compatible_engines(fmt)
        q = v.get("quality")
        tps = v.get("tokens_per_s")
        if not isinstance(q, (int, float)) or not 0.0 <= q <= 1.0:
            raise ValueError("quality must be between 0 and 1")
        if not isinstance(tps, (int, float)) or tps <= 0:
            raise ValueError("tokens_per_s must be positive")
        mem = v.get("memory_gb")
        estimated = mem is None
        if estimated:
            mem = estimate_memory_gb(params_b=params_b, bits=v.get("bits"))
        elif not isinstance(mem, (int, float)) or mem <= 0:
            raise ValueError("memory_gb must be positive")
        prepared[vid] = {
            "id": vid, "format": fmt, "bits": v.get("bits"), "quality": float(q),
            "tokens_per_s": float(tps), "memory_gb": float(mem), "memory_estimated": estimated, "engines": engines,
        }
    base = prepared.get(baseline_id)
    if base is None:
        raise ValueError("baseline_id is not among the variants")
    if base["quality"] <= 0:
        raise ValueError("baseline quality must be greater than 0")
    rows = []
    for row in prepared.values():
        rows.append({
            **row,
            "quality_loss": round((base["quality"] - row["quality"]) / base["quality"], 4),
            "speedup": round(row["tokens_per_s"] / base["tokens_per_s"], 4),
            "memory_saving": round(1.0 - row["memory_gb"] / base["memory_gb"], 4),
        })
    return {"baseline_id": baseline_id, "rows": rows}


def recommend(
    comparison: dict[str, Any],
    *,
    max_quality_loss: float,
    max_memory_gb: float | None = None,
    engine: str | None = None,
) -> dict[str, Any]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for row in comparison["rows"]:
        reasons = []
        if row["quality_loss"] > max_quality_loss:
            reasons.append("quality_loss_too_high")
        if max_memory_gb is not None and row["memory_gb"] > max_memory_gb:
            reasons.append("memory_too_high")
        if engine is not None and engine not in row["engines"]:
            reasons.append("engine_incompatible")
        if reasons:
            rejected.append({"id": row["id"], "reasons": reasons})
        else:
            accepted.append(row)
    best = max(accepted, key=lambda r: (r["tokens_per_s"], -r["memory_gb"])) if accepted else None
    return {"recommended_id": best["id"] if best else None, "rejected": rejected}


class VariantIn(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    format: str = Field(max_length=20)
    bits: int
    quality: float
    tokens_per_s: float
    memory_gb: float | None = None


class QuantCompareIn(BaseModel):
    variants: list[VariantIn] = Field(max_length=MAX_VARIANTS)
    baseline_id: str
    params_b: float
    max_quality_loss: float | None = Field(default=None, ge=0.0, le=1.0)
    max_memory_gb: float | None = Field(default=None, gt=0)
    engine: str | None = Field(default=None, max_length=30)


router = APIRouter(prefix="/api/v1/models/quantization", tags=["models"])


@router.post("/compare")
async def compare_api(body: QuantCompareIn, sess: dict = Depends(current_session)) -> dict[str, Any]:
    """FR-M5: compare quantized variants with a baseline; optionally recommend one under constraints."""
    require_scope(sess, "evals")
    try:
        result = compare_variants([v.model_dump() for v in body.variants], baseline_id=body.baseline_id, params_b=body.params_b)
    except ValueError as exc:
        raise AppError(400, str(exc)) from exc
    if body.max_quality_loss is not None:
        result["recommendation"] = recommend(
            result, max_quality_loss=body.max_quality_loss, max_memory_gb=body.max_memory_gb, engine=body.engine,
        )
    return result
