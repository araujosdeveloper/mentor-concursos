from apps.api.src.metrics import MetricsRegistry


def test_metrics_use_only_bounded_labels() -> None:
    registry = MetricsRegistry()
    registry.observe_request("GET", "/api/health/live", 200, 0.125)
    registry.record_auth_failure()
    registry.record_rate_limit_rejection()
    registry.set_readiness(True)

    rendered = registry.render()
    assert 'method="GET",route="/api/health/live",status="200"' in rendered
    assert "mentor_api_request_latency_seconds_sum" in rendered
    assert "mentor_api_auth_failures_total 1" in rendered
    assert "mentor_api_rate_limit_rejections_total 1" in rendered
    assert "mentor_api_ready 1" in rendered
