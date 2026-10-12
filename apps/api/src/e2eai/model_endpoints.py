"""Model endpoint registration and playground probes through LiteLLM (FR-M1).

This module keeps registration payloads secret-safe: external providers reference credentials through
`env:NAME` only, and playground responses never echo prompts or gateway keys. The actual persistent
admin model registry can store the returned gateway registration later; this P0 slice defines the
validated boundary and live-test path to the OpenAI-compatible gateway.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .auth import current_session, require_scope
from .core.config import get_settings
from .core.errors import AppError

_ALLOWED_ROLES = {"chat", "embedding", "reranker", "vision"}
_LOCAL_PROVIDERS = {"ollama", "vllm"}
_EXTERNAL_PROVIDERS = {"openai", "anthropic", "gemini"}
_PROVIDER_PREFIX = {
    "ollama": "ollama",
    "vllm": "openai",
    "openai": "openai",
    "anthropic": "anthropic",
    "gemini": "gemini",
}


def _require_text(value: Any, field: str, *, max_len: int = 200) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    value = value.strip()
    if len(value) > max_len:
        raise ValueError(f"{field} is too long")
    return value


def _model_ref(provider: str, model: str) -> str:
    prefix = _PROVIDER_PREFIX[provider]
    if model.startswith(f"{prefix}/"):
        return model
    return f"{prefix}/{model}"


def register_model_endpoint(spec: dict[str, Any]) -> dict[str, Any]:
    """Validate one local/external model endpoint and build a LiteLLM registration payload.

    Returned data is safe to store or show in an admin UI: it contains model ids, provider, role,
    and `env:` credential references only — never raw API keys.
    """
    if "api_key" in spec:
        raise ValueError("Use api_key_ref=env:NAME; raw api_key values are not accepted")
    endpoint_id = _require_text(spec.get("id"), "id", max_len=80)
    role = _require_text(spec.get("role"), "role", max_len=30)
    if role not in _ALLOWED_ROLES:
        raise ValueError("unsupported model role")
    provider = _require_text(spec.get("provider"), "provider", max_len=40)
    if provider not in _LOCAL_PROVIDERS | _EXTERNAL_PROVIDERS:
        raise ValueError("unsupported model provider")
    model = _require_text(spec.get("model"), "model", max_len=200)

    params: dict[str, Any] = {"model": _model_ref(provider, model)}
    if provider in _LOCAL_PROVIDERS:
        base_url = _require_text(spec.get("base_url"), "base_url", max_len=500)
        params["api_base"] = base_url.rstrip("/")
    else:
        ref = _require_text(spec.get("api_key_ref"), "api_key_ref", max_len=120)
        if not ref.startswith("env:") or len(ref) <= 4:
            raise ValueError("api_key_ref must be an env:NAME reference")
        params["api_key"] = ref
        if base_url := spec.get("base_url"):
            params["api_base"] = _require_text(base_url, "base_url", max_len=500).rstrip("/")

    return {
        "id": endpoint_id,
        "role": role,
        "provider": provider,
        "gateway": {
            "model_name": endpoint_id,
            "litellm_params": params,
        },
        "status": "registered_pending_gateway_apply",
    }


async def test_model_endpoint(
    client: Any,
    *,
    gateway_url: str,
    gateway_key: str,
    model: str,
    role: str,
    prompt: str,
) -> dict[str, Any]:
    """Probe LiteLLM using OpenAI-compatible chat or embeddings endpoints without echoing secrets."""
    model = _require_text(model, "model", max_len=120)
    role = _require_text(role, "role", max_len=30)
    if role not in _ALLOWED_ROLES:
        raise ValueError("unsupported model role")
    gateway_url = _require_text(gateway_url, "gateway_url", max_len=500).rstrip("/")
    gateway_key = _require_text(gateway_key, "gateway_key", max_len=500)
    prompt = _require_text(prompt, "prompt", max_len=4000)

    headers = {"Authorization": f"Bearer {gateway_key}"}
    if role == "embedding":
        response = await client.post(
            f"{gateway_url}/embeddings",
            headers=headers,
            json={"model": model, "input": prompt},
            timeout=15.0,
        )
        data = response.json()
        ok = getattr(response, "status_code", 200) < 400
        vector = (data.get("data") or [{}])[0].get("embedding") or []
        return {"ok": ok, "model": model, "role": role, "embedding_dimensions": len(vector), "usage": data.get("usage", {})}

    response = await client.post(
        f"{gateway_url}/chat/completions",
        headers=headers,
        json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0},
        timeout=30.0,
    )
    data = response.json()
    ok = getattr(response, "status_code", 200) < 400
    content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "")[:500]
    return {"ok": ok, "model": model, "role": role, "response_preview": content, "usage": data.get("usage", {})}


class ModelEndpointIn(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    role: str = Field(min_length=1, max_length=30)
    provider: str = Field(min_length=1, max_length=40)
    model: str = Field(min_length=1, max_length=200)
    base_url: str | None = Field(default=None, max_length=500)
    api_key_ref: str | None = Field(default=None, max_length=120)


class PlaygroundIn(BaseModel):
    model: str = Field(min_length=1, max_length=120)
    role: str = Field(default="chat", max_length=30)
    prompt: str = Field(min_length=1, max_length=4000)


router = APIRouter(prefix="/api/v1/admin/model-endpoints", tags=["admin"])


@router.post("/register")
async def register_api(body: ModelEndpointIn, sess: dict = Depends(current_session)) -> dict[str, Any]:
    require_scope(sess, "admin")
    try:
        return register_model_endpoint(body.model_dump(exclude_none=True))
    except ValueError as exc:
        raise AppError(400, str(exc)) from exc


@router.post("/playground")
async def playground_api(body: PlaygroundIn, sess: dict = Depends(current_session)) -> dict[str, Any]:
    require_scope(sess, "admin")
    settings = get_settings()
    try:
        async with httpx.AsyncClient() as client:
            return await test_model_endpoint(
                client,
                gateway_url=settings.litellm_url,
                gateway_key=settings.litellm_key,
                model=body.model,
                role=body.role,
                prompt=body.prompt,
            )
    except ValueError as exc:
        raise AppError(400, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise AppError(502, "Model gateway test failed") from exc
