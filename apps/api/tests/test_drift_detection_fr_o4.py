"""FR-O4 drift detection: query-topic shift, embedding drift, quality decay.

Deterministic/offline pure helpers; outputs carry only labels, numbers, and verdicts.
"""

import math

import pytest


def test_topic_shift_uses_jensen_shannon_and_psi():
    from e2eai.drift import topic_shift

    same = topic_shift({"hr": 50, "it": 50}, {"hr": 500, "it": 500})
    assert same["js_divergence"] == pytest.approx(0.0, abs=1e-9) and same["psi"] == pytest.approx(0.0, abs=1e-6)

    shifted = topic_shift({"hr": 90, "it": 10}, {"hr": 10, "it": 90})
    assert 0.5 < shifted["js_divergence"] <= 1.0 and shifted["psi"] > 0.25

    new = topic_shift({"hr": 100}, {"hr": 50, "payroll": 50})
    assert new["new_topics"] == ["payroll"] and new["vanished_topics"] == []
    with pytest.raises(ValueError):
        topic_shift({}, {"hr": 1})


def test_embedding_drift_centroid_cosine_and_spread():
    from e2eai.drift import embedding_drift

    base = [[1.0, 0.0], [0.9, 0.1], [1.0, 0.1]]
    same = embedding_drift(base, [[1.0, 0.05], [0.95, 0.1]])
    assert same["centroid_cosine_distance"] < 0.02

    moved = embedding_drift(base, [[0.0, 1.0], [0.1, 0.9]])
    assert moved["centroid_cosine_distance"] > 0.8
    assert math.isfinite(moved["spread_ratio"])
    with pytest.raises(ValueError):
        embedding_drift(base, [[1.0, 0.0, 0.0]])
    with pytest.raises(ValueError):
        embedding_drift([], base)


def test_quality_decay_flags_significant_drop():
    from e2eai.drift import quality_decay

    ok = quality_decay([0.8] * 100, [0.79] * 100, max_drop=0.05, min_samples=30)
    assert ok["decayed"] is False and ok["drop"] == pytest.approx(0.01)

    bad = quality_decay([0.8] * 100, [0.6] * 100, max_drop=0.05, min_samples=30)
    assert bad["decayed"] is True and bad["drop"] == pytest.approx(0.2)

    few = quality_decay([0.8] * 100, [0.1] * 5, max_drop=0.05, min_samples=30)
    assert few["decayed"] is False and few["reason"] == "insufficient_samples"


def test_detect_drift_combines_signals_and_never_echoes_queries():
    from e2eai.drift import detect_drift

    report = detect_drift(
        baseline={"topics": {"hr": 90, "it": 10}, "scores": [0.8] * 60, "embeddings": [[1.0, 0.0]] * 5},
        current={"topics": {"hr": 10, "it": 90}, "scores": [0.5] * 60, "embeddings": [[0.0, 1.0]] * 5,
                 "queries": ["secret question"]},
    )
    assert report["drifted"] is True
    assert set(report["signals_triggered"]) == {"topic_shift", "embedding_drift", "quality_decay"}
    assert "secret" not in str(report)

    calm = detect_drift(
        baseline={"topics": {"hr": 50, "it": 50}, "scores": [0.8] * 60},
        current={"topics": {"hr": 52, "it": 48}, "scores": [0.8] * 60},
    )
    assert calm["drifted"] is False and calm["signals_triggered"] == []
    assert "embedding_drift" not in calm["signals"]


def test_route_is_wired():
    from e2eai.main import app

    assert "post" in app.openapi()["paths"]["/api/v1/operate/drift"]
