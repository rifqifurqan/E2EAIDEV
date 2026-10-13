"""FR-F8 Tool adapter framework: standard interface + contract tests for every Lab tool.

Each Lab tool is expected to run in its own container (PRD §6). This module defines a standard
``ToolAdapter`` protocol that every container-side Lab tool implements, plus a registry and
contract tests that every registered adapter must satisfy: name, version, capabilities, health,
and a deterministic local mode for offline testing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ToolCapabilities:
    """Capabilities a Lab tool adapter advertises to the platform."""

    read_only: bool = False
    supports_cancel: bool = False
    supports_resume: bool = False
    max_input_bytes: int = 0
    streaming: bool = False


@dataclass
class AdapterHealth:
    """Health snapshot for a Lab tool adapter."""

    healthy: bool
    version: str = "0.0.0"
    detail: str = ""


class ToolAdapter(Protocol):
    """Standard interface every Lab tool adapter implements (FR-F8).

    A Lab tool runs in its own container; the host calls these methods over the adapter boundary.
    The protocol is structural so any object with these attributes satisfies it.
    """

    name: str
    version: str
    capabilities: ToolCapabilities

    def health(self) -> AdapterHealth: ...

    def configure(self, settings: dict) -> None:
        """Apply runtime settings (timeouts, model, etc.). No-op safe by default."""

    async def run(self, input: dict) -> dict:
        """Execute the tool and return a result dict."""


@dataclass
class RegisteredTool:
    """A Lab tool registered with the platform."""

    adapter: ToolAdapter
    container_name: str = ""
    env: dict = field(default_factory=dict)


class ToolAdapterRegistry:
    """Registry of Lab tool adapters with contract enforcement (FR-F8)."""

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, tool: ToolAdapter, *, container_name: str = "", env: dict | None = None) -> None:
        if not tool.name or not isinstance(tool.name, str):
            raise ValueError("ToolAdapter must have a non-empty string name")
        if not tool.version or not isinstance(tool.version, str):
            raise ValueError(f"ToolAdapter {tool.name!r} must have a non-empty string version")
        if not isinstance(getattr(tool, "capabilities", None), ToolCapabilities):
            raise ValueError(f"ToolAdapter {tool.name!r} must expose a ToolCapabilities instance")
        self._tools[tool.name] = RegisteredTool(adapter=tool, container_name=container_name, env=env or {})

    def get(self, name: str) -> ToolAdapter | None:
        registered = self._tools.get(name)
        return registered.adapter if registered else None

    def list(self) -> list[str]:
        return sorted(self._tools)

    def all(self) -> list[RegisteredTool]:
        return list(self._tools.values())

    def health(self) -> dict[str, AdapterHealth]:
        return {name: tool.adapter.health() for name, tool in self._tools.items()}


# ---------------------------------------------------------------------------
# Contract checks every registered adapter must satisfy
# ---------------------------------------------------------------------------


def check_adapter_contract(tool: ToolAdapter) -> None:
    """Assert a tool satisfies the FR-F8 adapter interface contract."""
    if not isinstance(tool.name, str) or not tool.name:
        raise AssertionError(f"Adapter name missing/empty: {tool!r}")
    if not isinstance(tool.version, str) or not tool.version:
        raise AssertionError(f"Adapter {tool.name!r} version missing/empty")
    if not isinstance(tool.capabilities, ToolCapabilities):
        raise AssertionError(f"Adapter {tool.name!r} capabilities is not a ToolCapabilities")
    health = tool.health()
    if not isinstance(health, AdapterHealth):
        raise AssertionError(f"Adapter {tool.name!r} health() did not return AdapterHealth")
    if not isinstance(health.version, str) or health.version != tool.version:
        raise AssertionError(f"Adapter {tool.name!r} health version {health.version!r} != {tool.version!r}")


def check_registry_contract(registry: ToolAdapterRegistry) -> None:
    """Assert every registered adapter passes the contract and names are unique."""
    for registered in registry.all():
        check_adapter_contract(registered.adapter)


async def run_tool_safely(registry: ToolAdapterRegistry, name: str, input: dict, *, timeout: float = 60.0) -> dict:
    """Run a Lab tool so that its failure degrades only its own feature (NFR-19).

    Never raises into the caller (chat stays up): a missing tool is ``unavailable``; a tool error,
    timeout or open circuit breaker is ``degraded`` with a short reason code. Exception text, hosts and
    keys are never copied into the result. Each tool has its own breaker (label ``lab:<name>``), so one
    broken tool cannot block another. Guardrails marked mandatory are handled elsewhere and still block.
    """
    import asyncio

    from .core.resilience import breaker_for

    tool = registry.get(name)
    if tool is None:
        return {"status": "unavailable", "tool": name, "reason": "tool_not_installed"}
    breaker = breaker_for(f"lab-tool:{name}", f"lab:{name}")
    if not breaker.allow():
        return {"status": "degraded", "tool": name, "reason": "tool_circuit_open",
                "retry_after": breaker.retry_after()}
    try:
        result = await asyncio.wait_for(tool.run(input), timeout=timeout)
    except TimeoutError:
        breaker.record_failure()
        return {"status": "degraded", "tool": name, "reason": "tool_timeout"}
    except Exception:  # noqa: BLE001 - a Lab tool must never take the caller down; details are dropped
        breaker.record_failure()
        return {"status": "degraded", "tool": name, "reason": "tool_error"}
    breaker.record_success()
    return {"status": "ok", "tool": name, "result": result}
