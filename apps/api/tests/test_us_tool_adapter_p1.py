"""FR-F8 Tool adapter framework: standard interface + contract tests for every Lab tool."""

from e2eai.tool_adapter import (
    AdapterHealth,
    ToolAdapterRegistry,
    ToolCapabilities,
    check_adapter_contract,
    check_registry_contract,
)
from e2eai.scan import LocalNoopScanner


def test_tool_capabilities_defaults_are_safe():
    caps = ToolCapabilities()
    assert caps.read_only is False
    assert caps.streaming is False
    assert caps.max_input_bytes == 0


class _GoodAdapter:
    name = "good"
    version = "2.1.0"
    capabilities = ToolCapabilities(read_only=True, streaming=True)

    def health(self) -> AdapterHealth:
        return AdapterHealth(healthy=True, version="2.1.0", detail="ok")

    def configure(self, settings: dict) -> None:
        pass

    async def run(self, input: dict) -> dict:
        return {"result": input}


class _BadName:
    name = ""
    version = "1.0.0"
    capabilities = ToolCapabilities()

    def health(self) -> AdapterHealth:
        return AdapterHealth(healthy=True, version="1.0.0")

    def configure(self, settings: dict) -> None:
        pass

    async def run(self, input: dict) -> dict:
        return {}


class _BadVersion:
    name = "bad-version"
    version = ""
    capabilities = ToolCapabilities()

    def health(self) -> AdapterHealth:
        return AdapterHealth(healthy=True, version="0.0.0")

    def configure(self, settings: dict) -> None:
        pass

    async def run(self, input: dict) -> dict:
        return {}


class _BadHealthVersion:
    name = "bad-health"
    version = "1.0.0"
    capabilities = ToolCapabilities()

    def health(self) -> AdapterHealth:
        return AdapterHealth(healthy=True, version="0.0.0")

    def configure(self, settings: dict) -> None:
        pass

    async def run(self, input: dict) -> dict:
        return {}


def test_check_adapter_contract_rejects_missing_name():
    try:
        check_adapter_contract(_BadName())  # type: ignore[arg-type]
        assert False, "should have raised"
    except AssertionError as exc:
        assert "name" in str(exc).lower()


def test_check_adapter_contract_rejects_missing_version():
    try:
        check_adapter_contract(_BadVersion())  # type: ignore[arg-type]
        assert False, "should have raised"
    except AssertionError as exc:
        assert "version" in str(exc).lower()


def test_check_adapter_contract_rejects_bad_health_version():
    try:
        check_adapter_contract(_BadHealthVersion())  # type: ignore[arg-type]
        assert False, "should have raised"
    except AssertionError as exc:
        assert "version" in str(exc).lower()


def test_check_adapter_contract_accepts_well_formed_adapter():
    check_adapter_contract(_GoodAdapter())


def test_registry_rejects_empty_name_and_allows_overwrite():
    registry = ToolAdapterRegistry()
    try:
        registry.register(_BadName())  # type: ignore[arg-type]
        assert False, "should have raised"
    except ValueError:
        pass
    registry.register(_GoodAdapter())
    assert "good" in registry.list()
    assert registry.get("good") is not None
    # Re-registering with the same name overwrites
    registry.register(_GoodAdapter())
    assert "good" in registry.list()


class _AdapterA:
    name = "adapter-a"
    version = "1.0.0"
    capabilities = ToolCapabilities(read_only=True)

    def health(self) -> AdapterHealth:
        return AdapterHealth(healthy=True, version="1.0.0", detail="a-ok")

    def configure(self, settings: dict) -> None:
        pass

    async def run(self, input: dict) -> dict:
        return {}


class _AdapterB:
    name = "adapter-b"
    version = "3.2.1"
    capabilities = ToolCapabilities(read_only=False)

    def health(self) -> AdapterHealth:
        return AdapterHealth(healthy=True, version="3.2.1")

    def configure(self, settings: dict) -> None:
        pass

    async def run(self, input: dict) -> dict:
        return {}


def test_registry_health_returns_per_adapter_snapshots():
    registry = ToolAdapterRegistry()
    registry.register(_AdapterA())
    registry.register(_AdapterB())
    health_map = registry.health()
    assert set(health_map) == {"adapter-a", "adapter-b"}
    assert health_map["adapter-a"].version == "1.0.0"
    assert health_map["adapter-b"].version == "3.2.1"


class _ScannerAdapter:
    """Bridge from Scanner protocol to the FR-F8 ToolAdapter interface."""

    def __init__(self, scanner) -> None:
        self._scanner = scanner
        self.name = "scan.local"
        self.version = "1.0.0"
        self.capabilities = ToolCapabilities(read_only=True, max_input_bytes=0)

    def health(self) -> AdapterHealth:
        return AdapterHealth(healthy=True, version=self.version, detail="noop")

    def configure(self, settings: dict) -> None:
        pass

    async def run(self, input: dict) -> dict:
        data = bytes(input.get("data", b""))
        result = await self._scanner.scan(data)
        return {"verdict": result.verdict, "signature": result.signature}


def test_registry_contract_passes_for_builtin_local_adapters():
    registry = ToolAdapterRegistry()
    noop = LocalNoopScanner()
    registry.register(_ScannerAdapter(noop))
    check_registry_contract(registry)
