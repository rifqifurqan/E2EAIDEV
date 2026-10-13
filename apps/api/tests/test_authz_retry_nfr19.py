"""NFR-19: OpenFGA checks retry transient failures briefly, and still fail closed."""

import asyncio

import httpx

from e2eai.authz import Authz


class _Resp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body if body is not None else {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=httpx.Request("POST", "http://x"), response=httpx.Response(self.status_code))


class _Script:
    """Returns/raises scripted outcomes in order; the last one repeats."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def post(self, *args, **kwargs):
        i = min(self.calls, len(self.outcomes) - 1)
        self.calls += 1
        out = self.outcomes[i]
        if isinstance(out, BaseException):
            raise out
        return out


def _authz(client):
    sleeps: list[float] = []

    async def fake_sleep(d):
        sleeps.append(d)

    a = Authz(client, "store", "model", sleep=fake_sleep)  # type: ignore[arg-type]
    return a, sleeps


def _check(a):
    return asyncio.run(a.check("user:andi", "viewer", "document:x"))


def test_transient_error_then_allowed_succeeds_after_retry():
    c = _Script(httpx.ConnectError("down"), _Resp(503), _Resp(200, {"allowed": True}))
    a, sleeps = _authz(c)
    assert _check(a) is True
    assert c.calls == 3 and len(sleeps) == 2


def test_persistent_outage_denies_after_bounded_attempts():
    c = _Script(httpx.ConnectTimeout("slow"))
    a, sleeps = _authz(c)
    assert _check(a) is False
    assert c.calls == 3  # bounded, not unlimited


def test_definitive_deny_is_never_retried():
    c = _Script(_Resp(200, {"allowed": False}))
    a, sleeps = _authz(c)
    assert _check(a) is False
    assert c.calls == 1 and sleeps == []


def test_client_errors_are_not_retried_and_deny():
    for status in (400, 401, 403, 404):
        c = _Script(_Resp(status))
        a, _ = _authz(c)
        assert _check(a) is False
        assert c.calls == 1, status


def test_malformed_success_body_denies():
    c = _Script(_Resp(200, {"allowed": "true"}))
    a, _ = _authz(c)
    assert _check(a) is False
