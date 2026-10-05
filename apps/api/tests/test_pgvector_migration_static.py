from pathlib import Path


def test_pgvector_migration_creates_extension_and_vector_column():
    migration = Path("migrations/versions/0004_pgvector_embeddings.py").read_text(encoding="utf-8")
    # The extension must be created (idempotently) so a fresh install gets pgvector without manual steps.
    assert "CREATE EXTENSION IF NOT EXISTS vector" in migration
    # chunk_embeddings.vector moves from jsonb to a real pgvector column.
    assert "Vector" in migration
    assert 'down_revision: str | Sequence[str] | None = "0003_chunk_embeddings"' in migration
