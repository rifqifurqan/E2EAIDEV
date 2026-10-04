"""OpenFGA model shape, drift-vs-DSL, and Authz.connect/check (PRD T4, NFR-19).

The live roundtrip runs only with E2EAI_LIVE=1 against the running stack."""

import asyncio
import os
import re

import pytest

from e2eai.authz import MODEL, MODEL_HASH, Authz, connect
from e2eai.core.config import repo_root

EXPECTED_TYPES = {"user", "org", "division", "team", "role", "guest", "folder", "document", "bot"}


def _types(model: dict) -> set[str]:
    return {t["type"] for t in model["type_definitions"]}


def test_model_shape_matches_prd_t4():
    assert MODEL["schema_version"] == "1.1"
    assert _types(MODEL) == EXPECTED_TYPES
    for shareable in ("folder", "document"):
        rels = next(t for t in MODEL["type_definitions"] if t["type"] == shareable)["relations"]
        assert {"parent", "owner", "editor", "viewer"} <= rels.keys()
    bot = next(t for t in MODEL["type_definitions"] if t["type"] == "bot")["relations"]
    assert {"admin", "user"} <= bot.keys()
    cond = MODEL["conditions"]["non_expired"]
    assert cond["expression"] == "current_time < expires_at"
    assert {"current_time", "expires_at"} == cond["parameters"].keys()


def test_model_hash_is_stable_sha256():
    assert re.fullmatch(r"[0-9a-f]{64}", MODEL_HASH)


def test_dsl_file_and_json_model_declare_the_same_types():
    """deploy/openfga/model.fga is the human-readable copy; guard it against drifting from the code."""
    dsl = (repo_root() / "deploy" / "openfga" / "model.fga").read_text(encoding="utf-8")
    dsl_types = {line.split()[1] for line in dsl.splitlines() if line.startswith("type ")}
    assert dsl_types == _types(MODEL)


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _CheckClient:
    def __init__(self, allowed):
        self._allowed = allowed

    async def post(self, *args, **kwargs):
        return _Resp({"allowed": self._allowed})


def test_check_returns_true_only_on_explicit_allowed():
    allow = Authz(_CheckClient(True), "store", "model")  # type: ignore[arg-type]
    deny = Authz(_CheckClient(False), "store", "model")  # type: ignore[arg-type]
    assert asyncio.run(allow.check("user:andi", "viewer", "document:x")) is True
    assert asyncio.run(deny.check("user:budi", "viewer", "document:x")) is False


class _FakeSetting:
    def __init__(self, value):
        self.value = value


class _FakeSession:
    def __init__(self, existing=None):
        self._existing = _FakeSetting(existing) if existing is not None else None
        self.added = None
        self.commits = 0

    async def get(self, _model, _key):
        return self._existing

    def add(self, obj):
        self.added = obj

    async def commit(self):
        self.commits += 1


class _ConnectClient:
    """Records calls so the test can assert store/model creation happened."""

    def __init__(self, stores=()):
        self._stores = list(stores)
        self.model_writes = 0

    async def get(self, path):
        assert path == "/stores"
        return _Resp({"stores": self._stores})

    async def post(self, path, json=None):
        if path == "/stores":
            return _Resp({"id": "store-new"})
        if path.endswith("/authorization-models"):
            self.model_writes += 1
            return _Resp({"authorization_model_id": "model-new"})
        raise AssertionError(f"unexpected POST {path}")


def test_connect_creates_store_and_writes_model(monkeypatch):
    import e2eai.authz as authz

    http = _ConnectClient(stores=[])
    monkeypatch.setattr(authz, "client", lambda settings: http)
    settings = type("S", (), {"openfga_store": "e2eai"})()
    session = _FakeSession(existing=None)

    result = asyncio.run(connect(settings, session))  # type: ignore[arg-type]
    assert isinstance(result, Authz)
    assert result.store_id == "store-new" and result.model_id == "model-new"
    assert http.model_writes == 1
    assert session.added.value["model_hash"] == MODEL_HASH
    assert session.commits == 1


def test_connect_is_idempotent_when_store_and_hash_match(monkeypatch):
    import e2eai.authz as authz

    http = _ConnectClient(stores=[])
    monkeypatch.setattr(authz, "client", lambda settings: http)
    settings = type("S", (), {"openfga_store": "e2eai"})()
    saved = {"store": "e2eai", "store_id": "store-1", "model_id": "model-1", "model_hash": MODEL_HASH}
    session = _FakeSession(existing=saved)

    result = asyncio.run(connect(settings, session))  # type: ignore[arg-type]
    assert result.store_id == "store-1" and result.model_id == "model-1"
    assert http.model_writes == 0  # nothing re-written when the hash is unchanged


@pytest.mark.skipif(not os.environ.get("E2EAI_LIVE"), reason="live OpenFGA; set E2EAI_LIVE=1")
def test_live_openfga_model_and_check():
    from e2eai.core.config import get_settings
    from e2eai.db import sessions

    async def run():
        async with sessions()() as session:
            authz = await connect(get_settings(), session)
        assert authz.store_id and authz.model_id
        # An unshared document denies (fail closed on a tuple that was never written).
        return await authz.check("user:nobody", "viewer", "document:does-not-exist")

    assert asyncio.run(run()) is False
