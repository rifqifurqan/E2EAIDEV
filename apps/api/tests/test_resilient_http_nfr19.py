"""NFR-19: external model/embedding/rerank calls retry transient failures and fail with a clear 503."""

import asyncio

import httpx
import pytest

from e2eai.core.errors import AppError
from e2eai.core.resilience import post_json_with_retry
from e2eai.retrieval import LiteLLMAnswerGenerator, LiteLLMEmbedder


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body or {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=self)  # type: ignore[arg-type]


def factory_for(script):
    """Each `post` pops the next scripted outcome: an exception to raise or a Resp to return."""
    calls = {"n": 0}

    class Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, path, headers=None, json=None):
            calls["n"] += 1
            item = script.pop(0)
            if isinstance(item, BaseException):
                raise item
            return item

    return Client, calls


async def _nosleep(d):
    pass


def _run(factory, **kw):
    return asyncio.run(post_json_with_retry(
        factory, base_url="http://x", timeout=1.0, path="/p", headers={}, json={}, sleep=_nosleep, **kw))


def test_retries_transport_error_then_succeeds():
    factory, calls = factory_for([httpx.ConnectError("refused"), Resp(200, {"ok": 1})])
    assert _run(factory).json() == {"ok": 1}
    assert calls["n"] == 2


def test_retries_503_then_succeeds_but_not_400():
    factory, calls = factory_for([Resp(503), Resp(200)])
    assert _run(factory).status_code == 200 and calls["n"] == 2
    factory, calls = factory_for([Resp(400)])
    assert _run(factory).status_code == 400 and calls["n"] == 1  # caller decides on client errors


def test_exhausted_retries_raise_clear_503_without_secrets():
    factory, calls = factory_for([httpx.ReadTimeout("slow")] * 3)
    with pytest.raises(AppError) as e:
        _run(factory, attempts=3)
    assert e.value.status == 503 and calls["n"] == 3
    assert "Bearer" not in str(e.value.detail)


def test_embedder_survives_one_transient_failure():
    ok = Resp(200, {"data": [{"embedding": [0.1, 0.2]}]})
    factory, calls = factory_for([httpx.ConnectError("refused"), ok])
    emb = LiteLLMEmbedder(base_url="http://x", api_key="k" * 20, model="m", client_factory=factory)
    # backoff uses the real sleep for the retry; keep it tiny by patching module default through attempts
    vectors = asyncio.run(emb.embed(["hello"]))
    assert vectors == [[0.1, 0.2]] and calls["n"] == 2


def test_answer_generator_gets_503_when_gateway_stays_down():
    factory, calls = factory_for([httpx.ConnectError("refused")] * 2)
    gen = LiteLLMAnswerGenerator(base_url="http://x", api_key="k" * 20, model="m", client_factory=factory)
    with pytest.raises(AppError) as e:
        asyncio.run(gen.generate("q", [], "en"))
    assert e.value.status == 503
