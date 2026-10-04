from pathlib import Path


def test_baseline_migration_is_reversible_and_covers_phase0_tables():
    migration = Path("migrations/versions/0001_phase0_baseline.py").read_text(encoding="utf-8")
    for table in [
        "organizations",
        "divisions",
        "teams",
        "users",
        "team_members",
        "roles",
        "user_roles",
        "local_credentials",
        "audit_log",
        "settings",
    ]:
        assert f'"{table}"' in migration
        assert f'op.drop_table("{table}")' in migration
    assert "op.create_index" in migration and "users_email_lower" in migration
