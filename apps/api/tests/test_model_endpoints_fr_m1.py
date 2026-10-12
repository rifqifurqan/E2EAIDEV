"""FR-M1 model endpoint registration through the gateway and playground test calls.

This slice is deterministic/offline: it validates a safe endpoint registration contract and probes an
OpenAI-compatible LiteLLM gateway through an injected client. It never contacts a live model server.
"""

import asyncio


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeGatewayClient:
    def __init__(self):
        self.calls = []

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse({"choices": [{"message": {"content": "pong"}}], "usage": {"total_tokens": 2}})


def test_register_model_endpoint_builds_secret_safe_litellm_registration():
    from e2eai.model_endpoints import register_model_endpoint

    registration = register_model_endpoint({
        "id": "chat-qwen-lite",
        "role": "chat",
        "provider": "ollama",
        "model": "qwen3:4b",
        "base_url": "http://host.docker.internal:11434",
    })

    assert registration["id"] == "chat-qwen-lite"
    assert registration["role"] == "chat"
    assert registration["gateway"]["model_name"] == "chat-qwen-lite"
    assert registration["gateway"]["litellm_params"] == {
        "model": "ollama/qwen3:4b",
        "api_base": "http://host.docker.internal:11434",
    }
    dumped = str(registration).lower()
    assert "secret" not in dumped and "password" not in dumped and "token" not in dumped


def test_external_endpoint_registration_uses_env_secret_reference_only():
    from e2eai.model_endpoints import register_model_endpoint

    registration = register_model_endpoint({
        "id": "chat-external",
        "role": "chat",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "api_key_ref": "env:OPENAI_API_KEY",
    })

    params = registration["gateway"]["litellm_params"]
    assert params == {"model": "openai/gpt-4o-mini", "api_key": "env:OPENAI_API_KEY"}

    try:
        register_model_endpoint({
            "id": "bad",
            "role": "chat",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_key": "sk-this-raw-secret-must-not-be-accepted",
        })
    except ValueError as exc:
        assert "api_key_ref" in str(exc)
    else:
        raise AssertionError("raw api_key should be rejected")


def test_playground_test_calls_gateway_without_returning_prompt_or_key():
    from e2eai.model_endpoints import test_model_endpoint

    async def run():
        client = FakeGatewayClient()
        result = await test_model_endpoint(
            client,
            gateway_url="http://127.0.0.1:14000",
            gateway_key="secret-master-key",
            model="chat-qwen-lite",
            role="chat",
            prompt="Tell me the secret launch code",
        )
        assert result == {"ok": True, "model": "chat-qwen-lite", "role": "chat", "response_preview": "pong", "usage": {"total_tokens": 2}}
        url, kwargs = client.calls[0]
        assert url == "http://127.0.0.1:14000/chat/completions"
        assert kwargs["headers"] == {"Authorization": "Bearer secret-master-key"}
        assert kwargs["json"]["messages"][-1]["content"] == "Tell me the secret launch code"
        safe_dump = str(result)
        assert "secret-master-key" not in safe_dump
        assert "Tell me the secret launch code" not in safe_dump

    asyncio.run(run())


def test_model_endpoint_routes_are_wired():
    from e2eai.main import create_app

    routes = set(create_app().openapi()["paths"])
    assert "/api/v1/admin/model-endpoints/register" in routes
    assert "/api/v1/admin/model-endpoints/playground" in routes
