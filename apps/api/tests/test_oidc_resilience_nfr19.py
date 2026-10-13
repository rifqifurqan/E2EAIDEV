"""NFR-19: Keycloak (OIDC) calls retry safely and fail with a clear 503, never leaking secrets."""

import asyncio

import httpx
import pytest

from e2eai.auth import OIDCProvider, exchange_oidc_code_for_identity
from e2eai.core.errors import AppError
from e2eai.core.resilience import reset_breakers

PROVIDER = OIDCProvider(
    authorization_endpoint="https://kc.local/auth",
    token_endpoint="https://kc.local/token",
    userinfo_endpoint="https://kc.local/userinfo",
    client_id="e2eai-web",
    client_secret="super-secret-client-value",
)


class Resp:
    def __init__(self, payload=None, status_code=200):
        self._p, self.status_code = payload or {}, status_code

    def json(self):
        return self._p


class Client:
    def __init__(self, posts, gets):
        self.posts, self.gets, self.post_n, self.get_n = list(posts), list(gets), 0, 0

    async def post(self, url, data, headers):
        self.post_n += 1
        item = self.posts.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    async def get(self, url, headers):
        self.get_n += 1
        item = self.gets.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


TOKEN = Resp({"access_token": "tok", "token_type": "Bearer"})
INFO = Resp({"sub": "s1", "email": "a@b.c", "name": "A"})


def run(client):
    reset_breakers()
    return asyncio.run(exchange_oidc_code_for_identity(
        client, PROVIDER, code="c", redirect_uri="https://app/cb", retry_sleep=_nosleep))


async def _nosleep(d):
    pass


def test_token_post_retries_connect_error_then_succeeds():
    client = Client([httpx.ConnectError("refused"), TOKEN], [INFO])
    assert run(client).email == "a@b.c"
    assert client.post_n == 2


def test_token_post_does_not_retry_read_timeout_because_code_is_single_use():
    client = Client([httpx.ReadTimeout("slow")], [INFO])
    with pytest.raises(AppError) as exc:
        run(client)
    assert exc.value.status == 503 and client.post_n == 1


def test_userinfo_get_retries_transport_errors():
    client = Client([TOKEN], [httpx.ReadTimeout("slow"), INFO])
    assert run(client).sub == "s1"
    assert client.get_n == 2


def test_keycloak_down_gives_clear_503_without_secrets():
    client = Client([httpx.ConnectError("refused")] * 3, [])
    with pytest.raises(AppError) as exc:
        run(client)
    err = exc.value
    assert err.status == 503
    assert "super-secret-client-value" not in f"{err.title} {err.detail}"


def test_rejected_code_is_still_401_and_not_retried():
    client = Client([Resp(status_code=400)], [])
    with pytest.raises(AppError) as exc:
        run(client)
    assert exc.value.status == 401 and client.post_n == 1


def _run_keep_breaker(client):
    return asyncio.run(exchange_oidc_code_for_identity(
        client, PROVIDER, code="c", redirect_uri="https://app/cb", retry_sleep=_nosleep))


def test_repeated_keycloak_outage_opens_breaker_and_fails_fast_with_retry_after():
    from e2eai.core.resilience import breaker_states

    reset_breakers()
    for _ in range(5):  # each failed login attempt = one breaker failure
        with pytest.raises(AppError):
            _run_keep_breaker(Client([httpx.ConnectError("refused")] * 3, []))
    assert breaker_states()["keycloak"] == 2  # open

    probe = Client([TOKEN], [INFO])
    with pytest.raises(AppError) as exc:
        _run_keep_breaker(probe)
    assert exc.value.status == 503 and probe.post_n == 0  # Keycloak not contacted
    assert int(exc.value.headers["Retry-After"]) >= 1
    assert "kc.local" not in f"{exc.value.title} {exc.value.detail}"
    reset_breakers()


def test_keycloak_rejections_and_success_do_not_trip_or_they_close_the_breaker():
    from e2eai.core.resilience import breaker_states

    reset_breakers()
    for _ in range(6):  # 4xx = IdP is up, the code was just bad
        with pytest.raises(AppError):
            _run_keep_breaker(Client([Resp(status_code=400)], []))
    assert breaker_states()["keycloak"] == 0
    assert _run_keep_breaker(Client([TOKEN], [INFO])).email == "a@b.c"
    assert breaker_states()["keycloak"] == 0
    reset_breakers()
