"""Characterization checks for extracted request/control/statistics helpers."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.services import execution, perf


def test_request_field_helper_keeps_render_order_and_live_secrets(monkeypatch):
    interface = SimpleNamespace(headers={"Authorization": "Bearer synthetic-token"},
                                params={"page": 1}, body={"password": "synthetic-password"})
    before = deepcopy(vars(interface))
    seen = []
    def render(value, context):
        seen.append(value)
        assert context == {"marker": 17}
        return deepcopy(value)
    monkeypatch.setattr(execution, "render_deep", render)
    secrets = {"previous-step-secret"}
    fields = execution._render_request_fields(interface, {"marker": 17}, secrets)
    assert seen == [interface.headers, interface.params, interface.body]
    assert fields == {"headers": interface.headers, "params": interface.params, "json": interface.body}
    assert fields["json"]["password"] == "synthetic-password"
    assert {"synthetic-token", "synthetic-password", "previous-step-secret"} <= secrets
    assert vars(interface) == before


def test_request_field_helper_preserves_none_fields():
    interface = SimpleNamespace(headers=None, params=None, body=None)
    secrets = set()
    assert execution._render_request_fields(interface, {}, secrets) == {
        "headers": None, "params": None, "json": None,
    }
    assert not secrets


def test_control_get_keeps_headers_timeout_and_status_before_json(monkeypatch):
    events = []
    monkeypatch.setattr(perf.settings, "LOCUST_CONTROL_TOKEN", "synthetic-control")
    monkeypatch.setattr(perf.settings, "REQUEST_TIMEOUT_SECONDS", 30)
    monkeypatch.setattr(perf.settings, "PERF_HEARTBEAT_TIMEOUT_SECONDS", 12)
    def get(url, **kwargs):
        events.append((url, kwargs))
        return SimpleNamespace(raise_for_status=lambda: events.append("status"),
                               json=lambda: events.append("json") or {"sample": 1})
    monkeypatch.setattr(perf.requests, "get", get)
    assert perf._control_get_json("http://synthetic.invalid", "/stats/requests") == {"sample": 1}
    assert events[0] == ("http://synthetic.invalid/stats/requests", {
        "headers": perf._control_headers(), "timeout": 3,
    })
    assert events[1:] == ["status", "json"]


def test_control_get_status_failure_does_not_decode_json(monkeypatch):
    monkeypatch.setattr(perf.settings, "LOCUST_CONTROL_TOKEN", "synthetic-control")
    def failure():
        raise RuntimeError("synthetic status failure")
    monkeypatch.setattr(perf.requests, "get", lambda *_a, **_kw: SimpleNamespace(
        raise_for_status=failure, json=lambda: pytest.fail("must not decode a failed response")))
    with pytest.raises(RuntimeError, match="status failure"):
        perf._control_get_json("http://synthetic.invalid", "/stats/requests")


@pytest.mark.parametrize("payload", [
    {"lease": "old", "configuration_failures": 0},
    {"lease": "current", "configuration_failures": 1}, {},
])
def test_iteration_handshake_still_rejects_stale_or_broken_configuration(payload):
    with pytest.raises(perf.PerfControlUnavailableError):
        perf._validate_iterations(payload, "current")


def test_iteration_handshake_accepts_matching_lease_without_failure_field():
    assert perf._validate_iterations({"lease": "current"}, "current") is None


@pytest.mark.parametrize("live_rps", [None, 0, 7])
def test_final_statistics_keep_live_rps_final_counts_percentiles_and_error_mapping(live_rps):
    stats = {"total_rps": 0, "fail_ratio": .25, "stats": [
        {"method": "GET", "name": "/a&b", "num_requests": 4, "num_failures": 1,
         "current_rps": 0, "95th_percentile": 15, "99th_percentile": 19},
        {"name": "Aggregated", "num_requests": 4, "avg_response_time": 10,
         "response_time_percentile_0.95": 16, "response_time_percentile_0.99": 20},
    ], "errors": [{"method": "GET", "name": "/a&amp;b", "occurrences": 1, "error": "synthetic"}]}
    before = deepcopy(stats)
    history = [{"elapsed_s": 4, "rps": 7}]
    result = perf._result_statistics(stats, live_rps, {("GET", "/a&b"): 7}, history)
    assert result["rps"] == (0 if live_rps is None else live_rps)
    assert result["request_stats"][0]["rps"] == 7
    assert result["request_stats"][0]["num_requests"] == 4
    assert result["request_stats"][0]["p95_response_ms"] == 15
    assert result["p95_response_ms"] == 16 and result["p99_response_ms"] == 20
    assert result["error_summary"][0]["name"] == "/a&b"
    assert result["error_summary"][0]["error_rate"] == .25
    assert result["history_samples"] is history and stats == before


@pytest.mark.parametrize("stats", [{}, {"stats": []}, {
    "stats": [{"name": "Aggregated", "num_requests": 0}],
}])
def test_final_statistics_still_reject_zero_traffic(stats):
    with pytest.raises(perf.PerfControlUnavailableError, match="请求"):
        perf._result_statistics(stats, None, {}, [])


def test_endpoint_counts_without_aggregate_remain_valid_with_optional_metrics_absent():
    result = perf._result_statistics({"stats": [{"method": "POST", "name": "/a", "num_requests": 1,
                                               "rps": 2}]}, None, {}, [])
    assert result["request_stats"][0]["rps"] == 2
    assert result["p95_response_ms"] is None
    assert result["history_samples"] is None and result["error_summary"] is None
