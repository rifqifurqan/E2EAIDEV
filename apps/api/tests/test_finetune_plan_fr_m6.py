"""FR-M6 fine-tuning and distillation (LoRA/QLoRA, DPO) with results fed back into benchmarking.

Deterministic/offline planning layer: validates a job spec (method, base model, dataset, hyperparameters),
estimates GPU memory, checks the training data is safe (labels only from approved sources, no raw PII),
renders a trainer-neutral config (Unsloth/Axolotl/TRL are adapters behind it), and turns a finished
run's metrics into benchmark-runner combinations so before/after can be compared. No training runs here.
"""

import pytest


def _spec(**over):
    spec = {
        "method": "qlora", "base_model": "qwen2.5-7b-instruct", "params_b": 7.0,
        "dataset": {"id": "ds-1", "version": 3, "kind": "fine_tuning", "examples": 1200},
        "hyperparameters": {"rank": 16, "alpha": 32, "learning_rate": 2e-4, "epochs": 3, "batch_size": 4, "max_seq_len": 2048},
    }
    spec.update(over)
    return spec


def test_valid_spec_produces_trainer_neutral_config_and_memory_estimate():
    from e2eai.finetune_plan import build_plan

    plan = build_plan(_spec())
    assert plan["method"] == "qlora" and plan["quantization_bits"] == 4
    assert plan["estimated_gpu_memory_gb"] > 4.0
    assert plan["trainer_config"]["lora"] == {"r": 16, "alpha": 32}
    assert plan["trainer_config"]["dataset"] == {"id": "ds-1", "version": 3}
    assert set(plan["supported_trainers"]) >= {"unsloth", "axolotl", "trl"}
    assert plan["steps_per_epoch"] == 300 and plan["total_steps"] == 900


def test_qlora_needs_less_memory_than_lora_and_full_ft_the_most():
    from e2eai.finetune_plan import build_plan

    q = build_plan(_spec(method="qlora"))["estimated_gpu_memory_gb"]
    l = build_plan(_spec(method="lora"))["estimated_gpu_memory_gb"]
    full = build_plan(_spec(method="full"))["estimated_gpu_memory_gb"]
    assert q < l < full


def test_dpo_requires_preference_dataset_and_distillation_requires_teacher():
    from e2eai.finetune_plan import build_plan

    with pytest.raises(ValueError):
        build_plan(_spec(method="dpo"))  # dataset kind is fine_tuning, not preference
    pref = _spec(method="dpo", dataset={"id": "p", "version": 1, "kind": "preference", "examples": 500})
    plan = build_plan(pref)
    assert plan["trainer_config"]["dpo"]["beta"] == 0.1

    with pytest.raises(ValueError):
        build_plan(_spec(method="distillation"))  # no teacher
    dist = build_plan(_spec(method="distillation", teacher_model="llama-3.3-70b"))
    assert dist["trainer_config"]["distillation"]["teacher"] == "llama-3.3-70b"


def test_invalid_specs_are_rejected():
    from e2eai.finetune_plan import build_plan

    base_h = _spec()["hyperparameters"]
    bad_specs = [
        _spec(method="pretrain"),
        _spec(base_model=""),
        _spec(params_b=0),
        _spec(dataset={"id": "d", "version": 1, "kind": "fine_tuning", "examples": 0}),
        _spec(dataset={"id": "d", "version": 1, "kind": "eval_only", "examples": 50}),
        _spec(hyperparameters={**base_h, "learning_rate": 5.0}),
        _spec(hyperparameters={**base_h, "epochs": 0}),
        _spec(hyperparameters={**base_h, "rank": 1024}),
        _spec(hyperparameters={**base_h, "batch_size": 0}),
    ]
    for bad in bad_specs:
        with pytest.raises(ValueError):
            build_plan(bad)


def test_plan_warns_on_small_data_and_oversized_gpu_budget():
    from e2eai.finetune_plan import build_plan

    small = build_plan(_spec(dataset={"id": "d", "version": 1, "kind": "fine_tuning", "examples": 40}))
    assert "dataset_small" in small["warnings"]
    fits = build_plan(_spec(), gpu_memory_gb=48)
    assert fits["fits_gpu"] is True and "exceeds_gpu_memory" not in fits["warnings"]
    tight = build_plan(_spec(method="full"), gpu_memory_gb=8)
    assert tight["fits_gpu"] is False and "exceeds_gpu_memory" in tight["warnings"]


def test_training_data_check_rejects_pii_and_unapproved_labels():
    from e2eai.finetune_plan import check_training_examples

    good = [{"prompt": "How many leave days?", "response": "20 days.", "label_source": "gold"}]
    assert check_training_examples(good)["ok"] is True
    bad = [
        {"prompt": "email me at jane@example.com", "response": "ok", "label_source": "gold"},
        {"prompt": "q", "response": "a", "label_source": "scraped"},
        {"prompt": "", "response": "a", "label_source": "gold"},
    ]
    res = check_training_examples(bad)
    assert res["ok"] is False
    assert {i["code"] for i in res["issues"]} == {"pii_detected", "label_source_not_approved", "empty_field"}
    assert "jane@example.com" not in str(res)  # indexes and codes only, never the text


def test_results_become_benchmark_combinations_for_before_after():
    from e2eai.finetune_plan import results_to_benchmark

    run = {
        "base_model": "qwen2.5-7b-instruct", "tuned_model": "qwen2.5-7b-hr-v1",
        "base_samples": [{"quality": 0.6, "latency_ms": 900, "output_tokens": 90}, {"quality": 0.7, "latency_ms": 1000, "output_tokens": 100}],
        "tuned_samples": [{"quality": 0.85, "latency_ms": 950, "output_tokens": 95}, {"quality": 0.9, "latency_ms": 1000, "output_tokens": 100}],
    }
    out = results_to_benchmark(run, prompt="hr-qa", dataset="hr-gold-v3")
    assert [c["model"] for c in out["combinations"]] == ["qwen2.5-7b-instruct", "qwen2.5-7b-hr-v1"]
    assert all(c["prompt"] == "hr-qa" and c["dataset"] == "hr-gold-v3" for c in out["combinations"])
    assert out["quality_delta"] == pytest.approx(0.225, abs=1e-4)
    # the combinations plug straight into the FR-T11 aggregation
    from e2eai.benchmark import summarize_combination

    assert summarize_combination(out["combinations"][1])["quality"] == pytest.approx(0.875, abs=1e-4)
    with pytest.raises(ValueError):
        results_to_benchmark({**run, "tuned_samples": []}, prompt="p", dataset="d")


def test_routes_wired():
    from e2eai.main import app

    paths = app.openapi()["paths"]
    assert "post" in paths["/api/v1/models/finetune/plan"]
    assert "post" in paths["/api/v1/models/finetune/check-data"]
    assert "post" in paths["/api/v1/models/finetune/results"]
