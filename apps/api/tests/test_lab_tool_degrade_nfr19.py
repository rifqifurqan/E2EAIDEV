"""NFR-19: a failing/slow Lab tool degrades its own feature (structured result), never raises into chat."""

import asyncio

from e2eai.core.resilience import CircuitBreaker, breaker_states, reset_breakers
from e2eai.tool_adapter import AdapterHealth, ToolAdapterRegistry, ToolCapabilities, run_tool_safely


class Tool:
    version = "1.0.0"
    capabilities = ToolCapabilities()

    def __init__(self, name, behaviour):
        self.name, self.behaviour, self.calls = name, behaviour, 0

    def health(self):
        return AdapterHealth(healthy=True, version=self.version)

    def configure(self, settings):
        pass

    async def run(self, input):
        self.calls += 1
        out = self.behaviour(input)
        if asyncio.iscoroutine(out):
            out = await out
        if isinstance(out, BaseException):
            raise out
        return out


def reg(*tools):
    r = ToolAdapterRegistry()
    for t in tools:
        r.register(t)
    return r


def run(coro):
    return asyncio.run(coro)


def test_success_returns_ok_with_result():
    reset_breakers()
    r = reg(Tool("ragas", lambda i: {"score": 0.9}))
    out = run(run_tool_safely(r, "ragas", {"q": 1}))
    assert out == {"status": "ok", "tool": "ragas", "result": {"score": 0.9}}


def test_unknown_tool_is_unavailable_not_an_exception():
    out = run(run_tool_safely(reg(), "nope", {}))
    assert out["status"] == "unavailable" and out["reason"] == "tool_not_installed"


def test_tool_error_degrades_without_leaking_exception_text():
    reset_breakers()
    r = reg(Tool("garak", lambda i: RuntimeError("boom at http://garak.internal:9000 key=sk-secret")))
    out = run(run_tool_safely(r, "garak", {}))
    assert out["status"] == "degraded" and out["reason"] == "tool_error" and "result" not in out
    assert "garak.internal" not in repr(out) and "sk-secret" not in repr(out)


def test_slow_tool_times_out_into_degraded():
    reset_breakers()

    async def slow(i):
        await asyncio.sleep(5)

    r = reg(Tool("slow", slow))
    out = run(run_tool_safely(r, "slow", {}, timeout=0.05))
    assert out["status"] == "degraded" and out["reason"] == "tool_timeout"


def test_repeated_failures_open_the_breaker_and_skip_the_tool_with_retry_after():
    reset_breakers()
    tool = Tool("flaky", lambda i: ConnectionError("down"))
    r = reg(tool)
    for _ in range(5):
        run(run_tool_safely(r, "flaky", {}))
    assert tool.calls == 5 and breaker_states()["lab:flaky"] == 2
    out = run(run_tool_safely(r, "flaky", {}))
    assert tool.calls == 5  # not called while the breaker is open
    assert out["status"] == "degraded" and out["reason"] == "tool_circuit_open" and out["retry_after"] >= 1


def test_one_tool_failing_does_not_affect_another_tool():
    reset_breakers()
    bad, good = Tool("bad", lambda i: ConnectionError("x")), Tool("good", lambda i: {"ok": True})
    r = reg(bad, good)
    for _ in range(6):
        run(run_tool_safely(r, "bad", {}))
    assert run(run_tool_safely(r, "good", {}))["status"] == "ok"
    assert breaker_states()["lab:good"] == 0
