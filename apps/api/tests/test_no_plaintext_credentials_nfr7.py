"""NFR-7: no plaintext credentials in the database. Schema-level guard.

Any column whose name looks like a credential must either be a hash/digest, or be on the reviewed allowlist
below (with the reason it is safe). A new credential-looking column fails this test until someone reviews it.
"""

import re

from e2eai.db import Base

CREDENTIAL_NAME = re.compile(r"(pass(word)?|secret|token|api_?key|credential|private|auth_config|salt)", re.I)
HASHY = re.compile(r"(hash|digest)$", re.I)

# (table, column): why it is safe
REVIEWED = {
    ("system_registrations", "auth_config"): "sanitized by system_registration.safe_config: mode/endpoint hints only",
    ("messages", "tokens"): "LLM token COUNT (an integer), not a credential",
}


def _hits():
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if CREDENTIAL_NAME.search(col.name):
                yield table.name, col.name, col


def test_credential_like_columns_are_hashes_or_reviewed():
    unreviewed = [
        f"{t}.{c}" for t, c, _ in _hits()
        if not HASHY.search(c) and (t, c) not in REVIEWED
    ]
    assert unreviewed == [], f"credential-looking columns need review: {unreviewed}"


def test_reviewed_allowlist_has_no_stale_entries():
    present = {(t, c) for t, c, _ in _hits()}
    assert set(REVIEWED) <= present


def test_hash_columns_are_not_long_enough_to_hold_raw_secrets_unhashed_by_accident():
    # password hashes are argon2 strings; API key and spec digests are sha256 hex (64 chars)
    for t, c, col in _hits():
        if HASHY.search(c) and (t, c) not in {("local_credentials", "password_hash")}:
            assert col.type.length in (64, None), f"{t}.{c} unexpected length {col.type.length}"


def test_live_database_contains_none_of_the_deployment_secret_values():
    """Scan every text/JSON column of the live DB for the secret values in deploy/compose/.env."""
    import asyncio

    import pytest
    from sqlalchemy import text

    from e2eai.core.config import repo_root
    from e2eai.db import sessions

    env = repo_root() / "deploy" / "compose" / ".env"
    if not env.exists():
        pytest.skip("no deploy/compose/.env on this machine")
    secrets = []
    for line in env.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            if len(value) >= 16 and any(m in key for m in ("PASSWORD", "KEY", "SECRET", "TOKEN")):
                secrets.append((key, value))
    assert secrets, "expected secrets in .env"

    async def run():
        leaks = []
        async with sessions()() as s:
            for table in Base.metadata.tables.values():
                cols = [c.name for c in table.columns if type(c.type).__name__ in ("String", "Text", "JSONB", "JSON", "VARCHAR")]
                if not cols:
                    continue
                expr = " || ' ' || ".join(f'coalesce("{c}"::text, \'\')' for c in cols)
                for key, value in secrets:
                    hit = await s.scalar(text(f'SELECT count(*) FROM "{table.name}" WHERE position(:v in ({expr})) > 0'), {"v": value})
                    if hit:
                        leaks.append((table.name, key))
        return leaks

    assert asyncio.run(run()) == []  # table and env KEY names only; values never printed
