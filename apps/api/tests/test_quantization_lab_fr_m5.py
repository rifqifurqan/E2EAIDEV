"""FR-M5 quantization lab: compare AWQ / GPTQ / GGUF on quality loss, speed, and memory.

Deterministic/offline: measurements are supplied by the caller (quality score, tokens/s, memory) per
variant; this module estimates memory when it is not measured, compares every variant with the
baseline, checks which serving engine can load each format, and recommends one under constraints.
"""

import pytest


def test_memory_estimate_scales_with_bits_and_includes_overhead():
    from e2eai.quantization_lab import estimate_memory_gb

    fp16 = estimate_memory_gb(params_b=7, bits=16)
    q4 = estimate_memory_gb(params_b=7, bits=4)
    assert fp16 == pytest.approx(7 * 2 * 1.1, rel=0.01) or fp16 > 14.0
    assert q4 < fp16 / 3 and q4 > 3.5  # 4-bit weights ~3.5 GB plus overhead
    with pytest.raises(ValueError):
        estimate_memory_gb(params_b=0, bits=4)
    with pytest.raises(ValueError):
        estimate_memory_gb(params_b=7, bits=3.5)


def test_format_engine_compatibility():
    from e2eai.quantization_lab import compatible_engines

    assert "vllm" in compatible_engines("awq") and "ollama" not in compatible_engines("awq")
    assert "vllm" in compatible_engines("gptq")
    assert set(compatible_engines("gguf")) >= {"ollama", "llamacpp"} and "vllm" not in compatible_engines("gguf")
    assert compatible_engines("fp16")  # baseline is loadable somewhere
    with pytest.raises(ValueError):
        compatible_engines("pickle-int4")


def _variants():
    return [
        {"id": "base", "format": "fp16", "bits": 16, "quality": 0.80, "tokens_per_s": 30.0, "memory_gb": 15.5},
        {"id": "awq4", "format": "awq", "bits": 4, "quality": 0.78, "tokens_per_s": 70.0, "memory_gb": 5.0},
        {"id": "gptq4", "format": "gptq", "bits": 4, "quality": 0.74, "tokens_per_s": 65.0},  # memory estimated
        {"id": "gguf-q8", "format": "gguf", "bits": 8, "quality": 0.795, "tokens_per_s": 40.0, "memory_gb": 8.5},
    ]


def test_compare_computes_loss_speedup_and_memory_saving_vs_baseline():
    from e2eai.quantization_lab import compare_variants

    res = compare_variants(_variants(), baseline_id="base", params_b=7)
    by_id = {r["id"]: r for r in res["rows"]}
    assert by_id["base"]["quality_loss"] == 0.0 and by_id["base"]["speedup"] == 1.0
    assert by_id["awq4"]["quality_loss"] == pytest.approx(0.025, abs=1e-4)  # relative to baseline 0.80
    assert by_id["awq4"]["speedup"] == pytest.approx(70 / 30, abs=1e-3)
    assert by_id["awq4"]["memory_saving"] == pytest.approx(1 - 5.0 / 15.5, abs=1e-3)
    assert by_id["gptq4"]["memory_gb"] > 3.5 and by_id["gptq4"]["memory_estimated"] is True
    assert by_id["awq4"]["memory_estimated"] is False
    assert by_id["gguf-q8"]["engines"] and "vllm" not in by_id["gguf-q8"]["engines"]
    assert res["baseline_id"] == "base"


def test_compare_rejects_bad_input():
    from e2eai.quantization_lab import compare_variants

    with pytest.raises(ValueError):
        compare_variants(_variants(), baseline_id="missing", params_b=7)
    with pytest.raises(ValueError):
        compare_variants([], baseline_id="base", params_b=7)
    dup = _variants() + [{"id": "awq4", "format": "awq", "bits": 4, "quality": 0.7, "tokens_per_s": 1.0}]
    with pytest.raises(ValueError):
        compare_variants(dup, baseline_id="base", params_b=7)
    zero_base = [{"id": "base", "format": "fp16", "bits": 16, "quality": 0.0, "tokens_per_s": 30.0}]
    with pytest.raises(ValueError):
        compare_variants(zero_base, baseline_id="base", params_b=7)
    with pytest.raises(ValueError):
        compare_variants([{"id": "base", "format": "fp16", "bits": 16, "quality": 1.5, "tokens_per_s": 1.0}], baseline_id="base", params_b=7)


def test_recommend_picks_fastest_within_quality_and_memory_limits():
    from e2eai.quantization_lab import compare_variants, recommend

    res = compare_variants(_variants(), baseline_id="base", params_b=7)
    rec = recommend(res, max_quality_loss=0.05, max_memory_gb=10.0)
    assert rec["recommended_id"] == "awq4"  # gptq4 loses ~7.5% quality, base is too big
    assert "gptq4" in {r["id"] for r in rec["rejected"]} and rec["rejected"][0]["reasons"]

    tight = recommend(res, max_quality_loss=0.001, max_memory_gb=4.0)
    assert tight["recommended_id"] is None and len(tight["rejected"]) >= 3

    engine = recommend(res, max_quality_loss=0.05, engine="ollama")
    assert engine["recommended_id"] == "gguf-q8"  # only GGUF loads on Ollama (baseline fp16 excluded)


def test_routes_wired():
    from e2eai.main import app

    assert "post" in app.openapi()["paths"]["/api/v1/models/quantization/compare"]
