"""P1 SLO metrics and alerting: latency, error rate, cost per conversation, guardrail trigger rate (FR-O5).

SLO metrics are computed from already-recorded chat/message/guardrail/audit-like event inputs.
Outputs are safe: only aggregated metrics and alert metadata — never raw prompts, answers,
document text, restricted titles/snippets, secrets, tokens, or credentials.
"""

import json

from e2eai.slo_metrics import (
    SloPolicy,
    check_slo_alerts,
    compute_slo_metrics,
)


# ---------- Sample event data for tests ----------

_EVENTS = [
    {"latency_ms": 120, "error": False, "cost_usd": 0.003, "guardrail_triggered": False, "tokens": 150},
    {"latency_ms": 200, "error": False, "cost_usd": 0.005, "guardrail_triggered": False, "tokens": 250},
    {"latency_ms": 450, "error": False, "cost_usd": 0.008, "guardrail_triggered": True, "tokens": 400},
    {"latency_ms": 95, "error": True, "cost_usd": 0.001, "guardrail_triggered": False, "tokens": 50},
    {"latency_ms": 310, "error": False, "cost_usd": 0.006, "guardrail_triggered": False, "tokens": 300},
    {"latency_ms": 180, "error": False, "cost_usd": 0.004, "guardrail_triggered": True, "tokens": 200},
    {"latency_ms": 600, "error": True, "cost_usd": 0.002, "guardrail_triggered": False, "tokens": 80},
    {"latency_ms": 140, "error": False, "cost_usd": 0.007, "guardrail_triggered": False, "tokens": 350},
    {"latency_ms": 250, "error": False, "cost_usd": 0.004, "guardrail_triggered": False, "tokens": 220},
    {"latency_ms": 170, "error": False, "cost_usd": 0.005, "guardrail_triggered": True, "tokens": 260},
]

_DEFAULT_POLICY = SloPolicy(
    latency_p50_ms=300,
    latency_p95_ms=800,
    error_rate=0.10,
    cost_per_conversation_usd=0.01,
    guardrail_trigger_rate=0.15,
)


# ---------- 1. compute_slo_metrics returns all four metric families ----------

def test_compute_slo_metrics_returns_latency_error_cost_guardrail():
    """compute_slo_metrics returns all four FR-O5 metric families: latency, error rate,
    cost per conversation, and guardrail trigger rate."""
    metrics = compute_slo_metrics(_EVENTS)

    assert "latency_p50_ms" in metrics
    assert "latency_p95_ms" in metrics
    assert "latency_mean_ms" in metrics
    assert "error_rate" in metrics
    assert "cost_per_conversation_usd" in metrics
    assert "guardrail_trigger_rate" in metrics
    assert "total_events" in metrics
    assert metrics["total_events"] == 10


# ---------- 2. latency percentile computation is correct ----------

def test_latency_percentiles_are_correct():
    """p50 and p95 latency are computed from the sorted latency values."""
    metrics = compute_slo_metrics(_EVENTS)

    # Sorted latencies: 95, 120, 140, 170, 180, 200, 250, 310, 450, 600
    # p50: rank=(50/100)*9=4.5 → lerp(180, 200, 0.5) = 190.0
    # p95: rank=(95/100)*9=8.55 → lerp(450, 600, 0.55) = 532.5
    assert metrics["latency_p50_ms"] == 190.0
    assert metrics["latency_p95_ms"] == 532.5
    assert metrics["latency_mean_ms"] == 251.5  # sum=2515, /10=251.5


# ---------- 3. error rate computation ----------

def test_error_rate_computation():
    """Error rate is the fraction of events where error=True."""
    metrics = compute_slo_metrics(_EVENTS)
    # 2 errors out of 10 events = 0.2
    assert metrics["error_rate"] == 0.2


# ---------- 4. cost per conversation ----------

def test_cost_per_conversation():
    """Cost per conversation is average cost_usd across events."""
    metrics = compute_slo_metrics(_EVENTS)
    # Total cost = 0.003+0.005+0.008+0.001+0.006+0.004+0.002+0.007+0.004+0.005 = 0.045
    # Average = 0.045 / 10 = 0.0045
    assert metrics["cost_per_conversation_usd"] == 0.0045


# ---------- 5. guardrail trigger rate ----------

def test_guardrail_trigger_rate():
    """Guardrail trigger rate is the fraction of events with guardrail_triggered=True."""
    metrics = compute_slo_metrics(_EVENTS)
    # 3 triggers out of 10 = 0.3
    assert metrics["guardrail_trigger_rate"] == 0.3


# ---------- 6. empty events produce safe zero defaults ----------

def test_empty_events_return_zero_metrics():
    """An empty event list returns zero for all metrics without division errors."""
    metrics = compute_slo_metrics([])
    assert metrics["total_events"] == 0
    assert metrics["latency_p50_ms"] == 0.0
    assert metrics["latency_p95_ms"] == 0.0
    assert metrics["latency_mean_ms"] == 0.0
    assert metrics["error_rate"] == 0.0
    assert metrics["cost_per_conversation_usd"] == 0.0
    assert metrics["guardrail_trigger_rate"] == 0.0


# ---------- 7. alert checks: all within SLO ----------

def test_check_slo_alerts_all_within_slo():
    """When all metrics are within thresholds, no alerts fire."""
    metrics = compute_slo_metrics(_EVENTS)
    # Use a lenient policy where everything passes
    lenient = SloPolicy(
        latency_p50_ms=500,
        latency_p95_ms=1000,
        error_rate=0.30,
        cost_per_conversation_usd=0.05,
        guardrail_trigger_rate=0.50,
    )
    alerts = check_slo_alerts(metrics, lenient)

    assert alerts["any_firing"] is False
    assert len(alerts["alerts"]) == 0
    # Five concrete checks: latency p50, latency p95, error rate, cost, and guardrail rate.
    assert alerts["total_checked"] == 5


# ---------- 8. alert checks: latency breaches ----------

def test_check_slo_alerts_latency_breach():
    """Alerts fire when latency metrics exceed configured SLO thresholds."""
    metrics = compute_slo_metrics(_EVENTS)
    # p50=190, p95=600 → set tight thresholds to trigger
    tight = SloPolicy(
        latency_p50_ms=100,
        latency_p95_ms=400,
        error_rate=1.0,
        cost_per_conversation_usd=1.0,
        guardrail_trigger_rate=1.0,
    )
    alerts = check_slo_alerts(metrics, tight)

    assert alerts["any_firing"] is True
    firing_names = {a["name"] for a in alerts["alerts"]}
    assert "latency_p50" in firing_names
    assert "latency_p95" in firing_names

    for alert in alerts["alerts"]:
        if alert["name"] == "latency_p50":
            assert alert["actual"] == 190.0
            assert alert["threshold"] == 100
        if alert["name"] == "latency_p95":
            assert alert["actual"] == 532.5
            assert alert["threshold"] == 400


# ---------- 9. alert checks: error rate breach ----------

def test_check_slo_alerts_error_rate_breach():
    """Alert fires when error rate exceeds the SLO threshold."""
    metrics = compute_slo_metrics(_EVENTS)
    tight = SloPolicy(
        latency_p50_ms=1000,
        latency_p95_ms=2000,
        error_rate=0.10,  # actual is 0.2 → breach
        cost_per_conversation_usd=1.0,
        guardrail_trigger_rate=1.0,
    )
    alerts = check_slo_alerts(metrics, tight)

    assert alerts["any_firing"] is True
    error_alerts = [a for a in alerts["alerts"] if a["name"] == "error_rate"]
    assert len(error_alerts) == 1
    assert error_alerts[0]["actual"] == 0.2
    assert error_alerts[0]["threshold"] == 0.10


# ---------- 10. alert checks: cost per conversation breach ----------

def test_check_slo_alerts_cost_breach():
    """Alert fires when cost per conversation exceeds the SLO threshold."""
    metrics = compute_slo_metrics(_EVENTS)
    tight = SloPolicy(
        latency_p50_ms=1000,
        latency_p95_ms=2000,
        error_rate=1.0,
        cost_per_conversation_usd=0.003,  # actual is 0.0045 → breach
        guardrail_trigger_rate=1.0,
    )
    alerts = check_slo_alerts(metrics, tight)

    assert alerts["any_firing"] is True
    cost_alerts = [a for a in alerts["alerts"] if a["name"] == "cost_per_conversation"]
    assert len(cost_alerts) == 1
    assert cost_alerts[0]["actual"] == 0.0045


# ---------- 11. alert checks: guardrail trigger rate breach ----------

def test_check_slo_alerts_guardrail_breach():
    """Alert fires when guardrail trigger rate exceeds the SLO threshold."""
    metrics = compute_slo_metrics(_EVENTS)
    tight = SloPolicy(
        latency_p50_ms=1000,
        latency_p95_ms=2000,
        error_rate=1.0,
        cost_per_conversation_usd=1.0,
        guardrail_trigger_rate=0.20,  # actual is 0.3 → breach
    )
    alerts = check_slo_alerts(metrics, tight)

    assert alerts["any_firing"] is True
    gr_alerts = [a for a in alerts["alerts"] if a["name"] == "guardrail_trigger_rate"]
    assert len(gr_alerts) == 1
    assert gr_alerts[0]["actual"] == 0.3


# ---------- 12. all four alert types fire simultaneously ----------

def test_check_slo_alerts_all_four_fire():
    """When all four thresholds are breached, all four alert types fire."""
    metrics = compute_slo_metrics(_EVENTS)
    strict = SloPolicy(
        latency_p50_ms=100,
        latency_p95_ms=400,
        error_rate=0.05,
        cost_per_conversation_usd=0.002,
        guardrail_trigger_rate=0.10,
    )
    alerts = check_slo_alerts(metrics, strict)

    assert alerts["any_firing"] is True
    firing_names = {a["name"] for a in alerts["alerts"]}
    assert firing_names == {"latency_p50", "latency_p95", "error_rate", "cost_per_conversation", "guardrail_trigger_rate"}


# ---------- 13. output safety: no raw content leaks ----------

def test_slo_metrics_output_contains_no_raw_content():
    """Metrics and alerts output must contain only numeric/boolean/string metadata —
    never raw prompts, answers, document text, secrets, or credentials."""
    metrics = compute_slo_metrics(_EVENTS)
    alerts = check_slo_alerts(metrics, _DEFAULT_POLICY)

    serialized = json.dumps({"metrics": metrics, "alerts": alerts}).lower()
    for forbidden in ("prompt", "answer", "secret", "password", "token", "credential",
                       "whatsapp", "revenue", "30 percent", "api_key", "bearer"):
        assert forbidden not in serialized, f"Forbidden term '{forbidden}' found in SLO output"


# ---------- 14. single event edge case ----------

def test_single_event_metrics():
    """A single event produces correct metrics (p50=p95=the value)."""
    events = [{"latency_ms": 300, "error": True, "cost_usd": 0.01, "guardrail_triggered": True, "tokens": 100}]
    metrics = compute_slo_metrics(events)

    assert metrics["total_events"] == 1
    assert metrics["latency_p50_ms"] == 300.0
    assert metrics["latency_p95_ms"] == 300.0
    assert metrics["latency_mean_ms"] == 300.0
    assert metrics["error_rate"] == 1.0
    assert metrics["cost_per_conversation_usd"] == 0.01
    assert metrics["guardrail_trigger_rate"] == 1.0


# ---------- 15. SloPolicy defaults ----------

def test_slo_policy_defaults():
    """SloPolicy has reasonable defaults so callers can override only what they need."""
    policy = SloPolicy()
    assert policy.latency_p50_ms > 0
    assert policy.latency_p95_ms > 0
    assert 0 < policy.error_rate <= 1.0
    assert policy.cost_per_conversation_usd > 0
    assert 0 < policy.guardrail_trigger_rate <= 1.0


# ---------- 16. API route wiring smoke test ----------

def test_slo_metrics_api_route_is_wired():
    """The /api/v1/operate/slo-metrics endpoint exists in the FastAPI app."""
    from e2eai.main import app

    openapi = app.openapi()
    assert "/api/v1/operate/slo-metrics" in openapi["paths"]
