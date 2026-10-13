"""Request metrics in Prometheus text format (NFR-16). No dependencies, no user data.

Labels are method, route *template* (or ``unmatched``) and status, so cardinality stays bounded and raw paths
(which may contain ids or emails) never appear. The registry is in-process; each worker exposes its own view.
"""

import threading
import time
from collections import defaultdict

BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.requests: dict[tuple[str, str, int], int] = defaultdict(int)
        self.buckets: dict[tuple[str, str], list[int]] = {}
        self.sums: dict[tuple[str, str], float] = defaultdict(float)
        self.counts: dict[tuple[str, str], int] = defaultdict(int)

    def observe(self, method: str, route: str, status: int, seconds: float) -> None:
        with self._lock:
            self.requests[(method, route, status)] += 1
            key = (method, route)
            counts = self.buckets.setdefault(key, [0] * len(BUCKETS))
            for i, bound in enumerate(BUCKETS):
                if seconds <= bound:
                    counts[i] += 1
            self.sums[key] += seconds
            self.counts[key] += 1


REGISTRY = MetricsRegistry()


def _fmt(value: float) -> str:
    return f"{value:g}"


def render_prometheus(reg: MetricsRegistry = REGISTRY) -> str:
    lines = ["# HELP http_requests_total Total HTTP requests.", "# TYPE http_requests_total counter"]
    with reg._lock:
        for (method, route, status), n in sorted(reg.requests.items()):
            lines.append(f'http_requests_total{{method="{method}",route="{route}",status="{status}"}} {n}')
        lines += ["# HELP http_request_duration_seconds HTTP request latency.",
                  "# TYPE http_request_duration_seconds histogram"]
        for (method, route), counts in sorted(reg.buckets.items()):
            base = f'method="{method}",route="{route}"'
            for bound, n in zip(BUCKETS, counts):
                lines.append(f'http_request_duration_seconds_bucket{{{base},le="{_fmt(bound)}"}} {n}')
            total = reg.counts[(method, route)]
            lines.append(f'http_request_duration_seconds_bucket{{{base},le="+Inf"}} {total}')
            lines.append(f'http_request_duration_seconds_sum{{{base}}} {_fmt(round(reg.sums[(method, route)], 6))}')
            lines.append(f'http_request_duration_seconds_count{{{base}}} {total}')
    from .resilience import breaker_states

    lines += ["# HELP circuit_breaker_state Upstream circuit breaker: 0 closed, 1 half-open, 2 open.",
              "# TYPE circuit_breaker_state gauge"]
    for upstream, value in sorted(breaker_states().items()):
        lines.append(f'circuit_breaker_state{{upstream="{upstream}"}} {value}')
    return "\n".join(lines) + "\n"


class MetricsMiddleware:
    def __init__(self, app, registry: MetricsRegistry | None = None):
        self.app, self.registry = app, registry or REGISTRY

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()
        status = {"code": 500}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            route = scope.get("route")
            template = getattr(route, "path", None) or "unmatched"
            self.registry.observe(scope["method"], template, status["code"], time.perf_counter() - start)
