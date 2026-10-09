"""FR-F12: API keys scoped by role — create, authenticate, revoke, scope enforcement.

TDD: these tests are written RED first, before the implementation exists."""

import asyncio
import hashlib
import secrets

from e2eai.auth import hash_password


class FakeRedis:
    """Minimal async stand-in for Valkey."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.expires: dict[str, int] = {}

    async def set(self, key, value, ex=None):
        self.store[key] = value
        if ex is not None:
            self.expires[key] = ex

    async def get(self, key):
        return self.store.get(key)

    async def delete(self, key):
        self.store.pop(key, None)
        self.expires.pop(key, None)

    async def expire(self, key, seconds):
        if key in self.store:
            self.expires[key] = seconds
            return True
        return False

    async def incr(self, key):
        self.store[key] = str(int(self.store.get(key, "0")) + 1)
        return int(self.store[key])


# ---------------------------------------------------------------------------
# 1. API key hashing: raw key is never stored, only its sha256
# ---------------------------------------------------------------------------


def test_api_key_hash_is_sha256_not_raw():
    from e2eai.api_keys import hash_api_key

    raw = secrets.token_urlsafe(32)
    hashed = hash_api_key(raw)
    assert hashed == hashlib.sha256(raw.encode()).hexdigest()
    assert raw not in hashed  # raw key never stored


def test_api_key_verify_matches_correct_key():
    from e2eai.api_keys import hash_api_key, verify_api_key

    raw = secrets.token_urlsafe(32)
    hashed = hash_api_key(raw)
    assert verify_api_key(raw, hashed) is True
    assert verify_api_key(raw + "x", hashed) is False
    assert verify_api_key("", hashed) is False


# ---------------------------------------------------------------------------
# 2. API key creation returns raw key once, stores only hash
# ---------------------------------------------------------------------------


def test_create_api_key_returns_raw_key_and_stores_hash():
    from e2eai.api_keys import create_api_key_sync

    result = create_api_key_sync(
        user_id="user-1",
        name="Test Key",
        scopes=["chat", "documents"],
    )
    assert "raw_key" in result
    assert result["raw_key"].startswith("e2eai_")
    assert "key_hash" in result
    assert result["raw_key"] not in result["key_hash"]
    assert result["name"] == "Test Key"
    assert result["scopes"] == ["chat", "documents"]
    assert "prefix" in result
    assert result["prefix"] == result["raw_key"][:12]


# ---------------------------------------------------------------------------
# 3. API key prefix extraction
# ---------------------------------------------------------------------------


def test_api_key_prefix_is_first_12_chars():
    from e2eai.api_keys import key_prefix

    raw = "e2eai_abc123456789xyz"
    assert key_prefix(raw) == "e2eai_abc123"


# ---------------------------------------------------------------------------
# 4. Scope validation
# ---------------------------------------------------------------------------


def test_valid_scopes_accepted():
    from e2eai.api_keys import VALID_SCOPES, validate_scopes

    assert validate_scopes(["chat", "documents"]) is True
    assert validate_scopes(list(VALID_SCOPES)) is True


def test_invalid_scopes_rejected():
    from e2eai.api_keys import validate_scopes

    assert validate_scopes([]) is False
    assert validate_scopes(["chat", "invalid_scope"]) is False
    assert validate_scopes(["admin"]) is False


# ---------------------------------------------------------------------------
# 5. Scope checking: key without required scope gets denied
# ---------------------------------------------------------------------------


def test_scope_check_grants_matching_scope():
    from e2eai.api_keys import has_scope

    assert has_scope(["chat", "documents"], "chat") is True
    assert has_scope(["chat", "documents"], "documents") is True


def test_scope_check_denies_missing_scope():
    from e2eai.api_keys import has_scope

    assert has_scope(["chat"], "documents") is False
    assert has_scope(["documents"], "evals") is False
    assert has_scope([], "chat") is False


# ---------------------------------------------------------------------------
# 6. Bearer token extraction from Authorization header
# ---------------------------------------------------------------------------


def test_extract_bearer_token():
    from e2eai.api_keys import extract_bearer_token

    assert extract_bearer_token("Bearer abc123") == "abc123"
    assert extract_bearer_token("bearer abc123") == "abc123"
    assert extract_bearer_token("Basic abc123") is None
    assert extract_bearer_token("") is None
    assert extract_bearer_token(None) is None
    assert extract_bearer_token("Bearer ") is None


# ---------------------------------------------------------------------------
# 7. Revoked or expired key must not authenticate
# ---------------------------------------------------------------------------


def test_revoked_key_info_is_marked():
    from e2eai.api_keys import is_key_usable

    from datetime import datetime, timedelta, UTC

    now = datetime.now(UTC)
    # Active key
    assert is_key_usable(revoked_at=None, expires_at=None) is True
    # Revoked key
    assert is_key_usable(revoked_at=now, expires_at=None) is False
    # Expired key
    assert is_key_usable(revoked_at=None, expires_at=now - timedelta(hours=1)) is False
    # Future expiry is fine
    assert is_key_usable(revoked_at=None, expires_at=now + timedelta(hours=1)) is True
