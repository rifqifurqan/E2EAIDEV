"""FR-F12 Python SDK: typed client tests with mocked transport (no live network)."""

import httpx
import pytest

from e2eai_sdk.client import E2EAIClient


def _mock_transport(status: int = 200, body: dict | None = None, capture: dict | None = None):
    async def handler(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture["method"] = request.method
            capture["url"] = str(request.url)
            capture["headers"] = dict(request.headers)
            capture["body"] = request.content.decode() if request.content else ""
        return httpx.Response(status, json=body or {})

    return httpx.MockTransport(handler)


def test_client_sets_auth_header():
    client = E2EAIClient(base_url="http://localhost:9000", api_key="e2eai_test123")
    assert client._api_key == "e2eai_test123"
    assert client._base_url == "http://localhost:9000"


def test_client_default_base_url():
    client = E2EAIClient(api_key="e2eai_test123")
    assert client._base_url == "http://localhost:8000"


@pytest.mark.asyncio
async def test_requests_include_bearer_header():
    captured: dict = {}
    client = E2EAIClient(base_url="http://test", api_key="e2eai_mykey", transport=_mock_transport(200, {}, captured))
    async with client:
        await client.health_check()
    assert captured["headers"]["authorization"] == "Bearer e2eai_mykey"


@pytest.mark.asyncio
async def test_chat_send_message():
    captured: dict = {}
    body = {"answer": "42", "citations": []}
    client = E2EAIClient(base_url="http://test", api_key="key1", transport=_mock_transport(200, body, captured))
    async with client:
        result = await client.chat_send("conv-1", "What is the answer?")
    assert result == body
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/api/v1/chat/conversations/conv-1/messages")
    assert "What is the answer?" in captured["body"]


@pytest.mark.asyncio
async def test_chat_list_conversations():
    body = {"conversations": [{"id": "c1", "title": "Test"}]}
    client = E2EAIClient(base_url="http://test", api_key="key1", transport=_mock_transport(200, body))
    async with client:
        result = await client.chat_list_conversations()
    assert result["conversations"][0]["id"] == "c1"


@pytest.mark.asyncio
async def test_document_search():
    captured: dict = {}
    body = {"results": [{"document_id": "d1", "title": "Test"}]}
    client = E2EAIClient(base_url="http://test", api_key="key1", transport=_mock_transport(200, body, captured))
    async with client:
        result = await client.document_search("test query")
    assert "results" in result
    assert "/api/v1/documents/search" in captured["url"]
    assert "q=test+query" in captured["url"]


@pytest.mark.asyncio
async def test_document_list():
    body = {"documents": []}
    client = E2EAIClient(base_url="http://test", api_key="key1", transport=_mock_transport(200, body))
    async with client:
        result = await client.document_list()
    assert result == body


@pytest.mark.asyncio
async def test_document_share():
    captured: dict = {}
    body = {"status": "ok"}
    client = E2EAIClient(base_url="http://test", api_key="key1", transport=_mock_transport(200, body, captured))
    async with client:
        result = await client.document_share("doc-1", "user:abc", "viewer")
    assert result["status"] == "ok"
    assert captured["url"].endswith("/api/v1/documents/doc-1/shares")
    assert "user:abc" in captured["body"]


@pytest.mark.asyncio
async def test_access_request_create():
    captured: dict = {}
    body = {"id": "req-1", "status": "pending"}
    client = E2EAIClient(base_url="http://test", api_key="key1", transport=_mock_transport(200, body, captured))
    async with client:
        result = await client.access_request_create("doc-1")
    assert result["status"] == "pending"
    assert "doc-1" in captured["body"]


@pytest.mark.asyncio
async def test_eval_create_dataset():
    body = {"id": "ds-1", "name": "test", "version": 1}
    client = E2EAIClient(base_url="http://test", api_key="key1", transport=_mock_transport(200, body))
    async with client:
        result = await client.eval_create_dataset("test", [{"q": "hi"}])
    assert result["name"] == "test"


@pytest.mark.asyncio
async def test_eval_run():
    body = {"id": "run-1", "metrics": {"score": 0.9}}
    client = E2EAIClient(base_url="http://test", api_key="key1", transport=_mock_transport(200, body))
    async with client:
        result = await client.eval_run("ds-1")
    assert "metrics" in result


@pytest.mark.asyncio
async def test_bot_ask():
    body = {"answer": "Hello", "citations": []}
    client = E2EAIClient(base_url="http://test", api_key="key1", transport=_mock_transport(200, body))
    async with client:
        result = await client.bot_ask("bot-1", "Hello?")
    assert result["answer"] == "Hello"


@pytest.mark.asyncio
async def test_bot_create():
    body = {"id": "bot-1", "name": "TestBot"}
    client = E2EAIClient(base_url="http://test", api_key="key1", transport=_mock_transport(200, body))
    async with client:
        result = await client.bot_create("TestBot")
    assert result["name"] == "TestBot"


@pytest.mark.asyncio
async def test_bot_release():
    body = {"id": "bundle-1", "version": 1, "status": "production"}
    client = E2EAIClient(base_url="http://test", api_key="key1", transport=_mock_transport(200, body))
    async with client:
        result = await client.bot_release("bot-1", {"model": "test"})
    assert result["status"] == "production"


@pytest.mark.asyncio
async def test_bot_grant():
    body = {"principal": "user:abc", "level": "user"}
    client = E2EAIClient(base_url="http://test", api_key="key1", transport=_mock_transport(200, body))
    async with client:
        result = await client.bot_grant("bot-1", "user:abc")
    assert result["principal"] == "user:abc"


@pytest.mark.asyncio
async def test_client_raises_on_error_status():
    client = E2EAIClient(base_url="http://test", api_key="bad_key", transport=_mock_transport(403, {"title": "Forbidden"}))
    async with client:
        with pytest.raises(httpx.HTTPStatusError):
            await client.chat_list_conversations()
