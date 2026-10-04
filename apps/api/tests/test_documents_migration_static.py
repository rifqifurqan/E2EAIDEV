from pathlib import Path


def test_documents_migration_covers_tables_and_is_reversible():
    migration = Path("migrations/versions/0002_documents.py").read_text(encoding="utf-8")
    for table in ["folders", "documents", "document_versions", "chunks", "doc_principals"]:
        assert f'"{table}"' in migration
        assert f'op.drop_table("{table}")' in migration
    # doc_principals is the read-index: PK(document_id, principal) + index(principal, document_id) per T4.
    assert "doc_principals_by_principal" in migration
    assert 'down_revision: str | Sequence[str] | None = "0001_phase0_baseline"' in migration
