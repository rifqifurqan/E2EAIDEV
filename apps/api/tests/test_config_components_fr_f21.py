"""FR-F21 / FR-R3: invalid `components` in e2eai.yaml fail at startup with a clear message."""

import pytest

from e2eai.core.config import ConfigError, get_settings, validate_components


def test_valid_components_pass_and_defaults_are_local_pgvector_celery():
    assert validate_components({"components": {"auth": "oidc", "job_engine": "temporal", "vector_store": "qdrant"}}) == {
        "auth": "oidc", "job_engine": "temporal", "vector_store": "qdrant", "tracing": "postgres"}
    assert validate_components({}) == {"auth": "local", "job_engine": "celery", "vector_store": "pgvector",
                                       "tracing": "postgres"}


def test_unknown_vector_store_fails_with_allowed_values_listed():
    with pytest.raises(ConfigError) as exc:
        validate_components({"components": {"vector_store": "pinecone"}})
    msg = str(exc.value)
    assert "components.vector_store" in msg and "pinecone" in msg and "pgvector" in msg and "qdrant" in msg


def test_all_bad_components_are_reported_together():
    with pytest.raises(ConfigError) as exc:
        validate_components({"components": {"auth": "ldap", "job_engine": "rq", "vector_store": "x"}})
    msg = str(exc.value)
    assert "components.auth" in msg and "components.job_engine" in msg and "components.vector_store" in msg


def test_non_mapping_components_is_rejected():
    with pytest.raises(ConfigError):
        validate_components({"components": ["pgvector"]})


def test_settings_expose_the_selected_stores():
    s = get_settings()
    assert s.vector_store in {"pgvector", "qdrant"} and s.job_engine in {"celery", "temporal"}
