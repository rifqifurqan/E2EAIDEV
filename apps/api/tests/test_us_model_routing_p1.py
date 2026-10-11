from e2eai.model_routing import ModelRoutingConfig, classify_query_complexity, route_model


def test_simple_short_question_routes_to_small_model() -> None:
    cfg = ModelRoutingConfig(small_model="qwen-small", large_model="qwen-large")

    assert route_model(query="What is the leave policy?", settings=cfg) == "qwen-small"


def test_long_multi_part_question_routes_to_large_model() -> None:
    cfg = ModelRoutingConfig(small_model="qwen-small", large_model="qwen-large")
    query = " ".join(["Compare quarterly revenue, explain anomalies, cite constraints, and propose next actions"] * 8)

    assert route_model(query=query, settings=cfg) == "qwen-large"


def test_technical_keywords_route_to_large_model() -> None:
    cfg = ModelRoutingConfig(small_model="qwen-small", large_model="qwen-large")

    assert route_model(query="Debug the async SQLAlchemy migration rollback and OAuth token exchange", settings=cfg) == "qwen-large"


def test_empty_query_uses_safe_large_fallback() -> None:
    cfg = ModelRoutingConfig(small_model="qwen-small", large_model="qwen-large")

    assert route_model(query="   ", settings=cfg) == "qwen-large"


def test_explicit_complexity_score_overrides_heuristic() -> None:
    cfg = ModelRoutingConfig(small_model="qwen-small", large_model="qwen-large", large_threshold=7)

    assert route_model(query="simple words", settings=cfg, complexity_score=8) == "qwen-large"
    assert route_model(query="complex oauth kubernetes postgres", settings=cfg, complexity_score=1) == "qwen-small"


def test_complexity_classifier_is_deterministic_and_bounded() -> None:
    score = classify_query_complexity("Explain Kubernetes rollback strategy with database migration risk")

    assert 0 <= score <= 10
    assert score >= 7
