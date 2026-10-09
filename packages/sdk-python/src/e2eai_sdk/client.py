"""Async Python client for the E2EAIDEV public REST API (FR-F12)."""

from __future__ import annotations

from typing import Any

import httpx


class E2EAIClient:
    """Small async SDK client using Bearer API-key auth.

    The client is intentionally lightweight: callers can inject an ``httpx.AsyncBaseTransport``
    for tests and keep using the same wrapper methods against a live API in production.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "http://localhost:8000",
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._transport = transport
        self._timeout = timeout
        self._http: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "E2EAIClient":
        self._ensure_client()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self._base_url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                transport=self._transport,
                timeout=self._timeout,
            )
        return self._http

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = await self._ensure_client().request(method, path, **kwargs)
        response.raise_for_status()
        if response.content:
            data = response.json()
            return data if isinstance(data, dict) else {"data": data}
        return {}

    async def health_check(self) -> dict[str, Any]:
        return await self._request("GET", "/api/v1/health")

    # Chat
    async def chat_list_conversations(self) -> dict[str, Any]:
        return await self._request("GET", "/api/v1/chat/conversations")

    async def chat_send(self, conversation_id: str, question: str, **extra: Any) -> dict[str, Any]:
        payload = {"question": question, **extra}
        return await self._request("POST", f"/api/v1/chat/conversations/{conversation_id}/messages", json=payload)

    # Documents and sharing
    async def document_list(self, view: str = "shared_with_me") -> dict[str, Any]:
        return await self._request("GET", "/api/v1/documents", params={"view": view})

    async def document_search(self, query: str, **params: Any) -> dict[str, Any]:
        return await self._request("GET", "/api/v1/documents/search", params={"q": query, **params})

    async def document_share(
        self,
        document_id: str,
        principal: str,
        level: str = "viewer",
        expires_at: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"principal": principal, "level": level}
        if expires_at is not None:
            payload["expires_at"] = expires_at
        return await self._request("POST", f"/api/v1/documents/{document_id}/shares", json=payload)

    async def access_request_create(self, document_id: str) -> dict[str, Any]:
        return await self._request("POST", "/api/v1/documents/access-requests", json={"document_id": document_id})

    async def access_request_list(self) -> dict[str, Any]:
        return await self._request("GET", "/api/v1/documents/access-requests")

    async def access_request_approve(self, request_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/api/v1/documents/access-requests/{request_id}/approve")

    async def access_request_deny(self, request_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/api/v1/documents/access-requests/{request_id}/deny")

    # Evals
    async def eval_create_dataset(self, name: str, items: list[dict[str, Any]], source: str = "sdk") -> dict[str, Any]:
        return await self._request("POST", "/api/v1/evals/datasets", json={"name": name, "items": items, "source": source})

    async def eval_run(self, dataset_id: str, adapter: str = "local-ragas") -> dict[str, Any]:
        return await self._request("POST", "/api/v1/evals/runs", json={"dataset_id": dataset_id, "adapter": adapter})

    # Bots
    async def bot_create(self, name: str) -> dict[str, Any]:
        return await self._request("POST", "/api/v1/bots", json={"name": name})

    async def bot_ask(self, bot_id: str, question: str) -> dict[str, Any]:
        return await self._request("POST", f"/api/v1/bots/{bot_id}/ask", json={"question": question})

    async def bot_release(self, bot_id: str, bundle: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", f"/api/v1/bots/{bot_id}/bundles", json={"bundle": bundle})

    async def bot_grant(self, bot_id: str, principal: str, level: str = "user") -> dict[str, Any]:
        return await self._request("POST", f"/api/v1/bots/{bot_id}/grants", json={"principal": principal, "level": level})
