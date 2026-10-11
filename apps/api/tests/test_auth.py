import asyncio
import uuid

from e2eai.auth import (
    LOGIN_MAX_ATTEMPTS,
    OIDCIdentity,
    OIDCProvider,
    Sessions,
    build_oidc_authorization_url,
    complete_oidc_login,
    csrf_ok,
    ensure_oidc_user,
    exchange_oidc_code_for_identity,
    hash_password,
    local_login_allowed,
    login_allowed,
    new_token,
    verify_password,
)


class FakeRedis:
    """Minimal async stand-in: the handful of commands the session store and rate limit use."""

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


def test_password_hash_is_argon2id_and_round_trips():
    h = hash_password("correct horse")
    assert h.startswith("$argon2id$")
    assert verify_password(h, "correct horse") is True
    assert verify_password(h, "wrong") is False
    assert verify_password("not-a-hash", "whatever") is False


def test_csrf_token_compare():
    token = new_token()
    assert csrf_ok(token, token) is True
    assert csrf_ok(token, token + "x") is False
    assert csrf_ok("", "") is False  # a missing session token never validates


def test_login_rate_limit_blocks_after_max_attempts():
    redis = FakeRedis()

    async def run():
        allowed = [await login_allowed(redis, "andi@demo.e2eai") for _ in range(LOGIN_MAX_ATTEMPTS + 2)]
        return allowed

    allowed = asyncio.run(run())
    assert all(allowed[:LOGIN_MAX_ATTEMPTS]) and not any(allowed[LOGIN_MAX_ATTEMPTS:])
    assert redis.expires["login_rl:andi@demo.e2eai"] == 300  # window set once, on the first attempt


def test_session_create_get_delete_with_sliding_ttl():
    redis = FakeRedis()
    store = Sessions(redis, idle_seconds=8 * 3600)

    async def run():
        sid, csrf = await store.create("user-1")
        assert redis.expires[f"sess:{sid}"] == 8 * 3600
        redis.expires[f"sess:{sid}"] = 1  # pretend time passed
        data = await store.get(sid)
        assert data == {"user_id": "user-1", "csrf": csrf}
        assert redis.expires[f"sess:{sid}"] == 8 * 3600  # get() slid the idle window back out
        await store.delete(sid)
        return await store.get(sid)

    assert asyncio.run(run()) is None


def test_oidc_authorization_url_is_secret_free_and_state_bound():
    provider = OIDCProvider(
        authorization_endpoint="https://idp.example/realms/e2eai/protocol/openid-connect/auth",
        client_id="e2eai-web",
    )

    url = build_oidc_authorization_url(
        provider,
        redirect_uri="https://app.example/api/v1/auth/oidc/callback",
        state="state-token",
        nonce="nonce-token",
        code_challenge="pkce-challenge",
    )

    assert url.startswith("https://idp.example/realms/e2eai/protocol/openid-connect/auth?")
    assert "response_type=code" in url
    assert "client_id=e2eai-web" in url
    assert "state=state-token" in url
    assert "nonce=nonce-token" in url
    assert "code_challenge=pkce-challenge" in url
    assert "client_secret" not in url.lower()


def test_oidc_mode_local_password_login_is_break_glass_only():
    assert local_login_allowed("local", oidc_available=False, is_break_glass_user=False) is True
    assert local_login_allowed("oidc", oidc_available=True, is_break_glass_user=False) is False
    assert local_login_allowed("oidc", oidc_available=False, is_break_glass_user=False) is False
    assert local_login_allowed("oidc", oidc_available=False, is_break_glass_user=True) is True


def test_oidc_code_exchange_uses_keycloak_token_and_userinfo_without_leaking_secret():
    class FakeResponse:
        def __init__(self, payload, status_code=200):
            self._payload = payload
            self.status_code = status_code
            self.text = "[redacted]"

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self):
            self.posts = []
            self.gets = []

        async def post(self, url, data, headers):
            self.posts.append({"url": url, "data": data, "headers": headers})
            return FakeResponse({"access_token": "access-token", "token_type": "Bearer"})

        async def get(self, url, headers):
            self.gets.append({"url": url, "headers": headers})
            return FakeResponse({"sub": "keycloak-user-1", "email": "Andi@Demo.E2EAI", "name": "Andi Sales"})

    provider = OIDCProvider(
        authorization_endpoint="https://keycloak.local/realms/e2eai/protocol/openid-connect/auth",
        token_endpoint="https://keycloak.local/realms/e2eai/protocol/openid-connect/token",
        userinfo_endpoint="https://keycloak.local/realms/e2eai/protocol/openid-connect/userinfo",
        client_id="e2eai-web",
        client_secret="super-secret-client-value",
    )
    client = FakeClient()

    identity = asyncio.run(exchange_oidc_code_for_identity(
        client,
        provider,
        code="auth-code",
        redirect_uri="https://app.example/api/v1/auth/oidc/callback",
        code_verifier="pkce-verifier",
    ))

    assert identity == OIDCIdentity(sub="keycloak-user-1", email="andi@demo.e2eai", display_name="Andi Sales")
    assert client.posts == [{
        "url": provider.token_endpoint,
        "data": {
            "grant_type": "authorization_code",
            "code": "auth-code",
            "redirect_uri": "https://app.example/api/v1/auth/oidc/callback",
            "client_id": "e2eai-web",
            "client_secret": "super-secret-client-value",
            "code_verifier": "pkce-verifier",
        },
        "headers": {"Content-Type": "application/x-www-form-urlencoded"},
    }]
    assert client.gets == [{
        "url": provider.userinfo_endpoint,
        "headers": {"Authorization": "Bearer access-token"},
    }]
    assert "super-secret-client-value" not in repr(provider)
    assert "access-token" not in repr(identity)


def test_oidc_identity_creates_or_reuses_active_user_without_local_password():
    from e2eai.db import User

    class FakeSession:
        def __init__(self, result):
            self.result = result
            self.added = []
            self.flushes = 0

        async def scalar(self, statement):
            return self.result

        def add(self, obj):
            self.added.append(obj)

        async def flush(self):
            self.flushes += 1

    org_id = uuid.uuid4()
    identity = OIDCIdentity(sub="kc-1", email="andi@demo.e2eai", display_name="Andi Sales")
    created_session = FakeSession(result=None)
    user = asyncio.run(ensure_oidc_user(created_session, identity, default_org_id=org_id))

    assert isinstance(user, User)
    assert user.email == "andi@demo.e2eai"
    assert user.display_name == "Andi Sales"
    assert user.org_id == org_id
    assert user.status == "active"
    assert created_session.added == [user]
    assert created_session.flushes == 1

    existing = User(org_id=org_id, email="andi@demo.e2eai", display_name="Existing Andi", status="active")
    reused_session = FakeSession(result=existing)
    assert asyncio.run(ensure_oidc_user(reused_session, identity, default_org_id=org_id)) is existing
    assert reused_session.added == []
    assert reused_session.flushes == 0


def test_complete_oidc_login_exchanges_code_creates_user_and_session():
    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload
            self.status_code = 200
            self.text = "[redacted]"

        def json(self):
            return self._payload

    class FakeClient:
        async def post(self, url, data, headers):
            return FakeResponse({"access_token": "access-token", "token_type": "Bearer"})

        async def get(self, url, headers):
            return FakeResponse({"sub": "keycloak-user-1", "email": "andi@demo.e2eai", "name": "Andi Sales"})

    class FakeSession:
        async def scalar(self, statement):
            return None

        def add(self, obj):
            self.user = obj

        async def flush(self):
            self.user.id = uuid.uuid4()

    class FakeSessions:
        async def create(self, user_id):
            self.created_for = user_id
            return "sid-token", "csrf-token"

    provider = OIDCProvider(
        authorization_endpoint="https://keycloak.local/realms/e2eai/protocol/openid-connect/auth",
        token_endpoint="https://keycloak.local/realms/e2eai/protocol/openid-connect/token",
        userinfo_endpoint="https://keycloak.local/realms/e2eai/protocol/openid-connect/userinfo",
        client_id="e2eai-web",
    )
    session_store = FakeSessions()
    user, sid, csrf = asyncio.run(complete_oidc_login(
        FakeSession(),
        session_store,
        FakeClient(),
        provider,
        code="auth-code",
        redirect_uri="https://app.example/api/v1/auth/oidc/callback",
        default_org_id=uuid.uuid4(),
    ))

    assert user.email == "andi@demo.e2eai"
    assert session_store.created_for == str(user.id)
    assert sid == "sid-token"
    assert csrf == "csrf-token"

