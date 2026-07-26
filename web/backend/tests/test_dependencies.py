from app.services import dependencies


def test_api_health_uses_delegated_backtest_worker_without_docker_socket(monkeypatch):
    monkeypatch.setattr(dependencies, "BACKTEST_EXECUTION_DELEGATED", True)
    monkeypatch.setattr(
        dependencies,
        "check_database",
        lambda: {"service": "database", "ok": True, "detail": {}},
    )
    monkeypatch.setattr(
        dependencies,
        "check_redis",
        lambda: {"service": "redis", "ok": True, "detail": {}},
    )
    monkeypatch.setattr(
        dependencies.market_data,
        "ping",
        lambda: {"service": "clickhouse", "ok": True, "detail": {}},
    )
    monkeypatch.setattr(
        dependencies,
        "check_backtest_worker",
        lambda: {
            "service": "backtest_worker",
            "ok": True,
            "detail": {"mode": "delegated", "workers": ["backtest@worker"]},
        },
    )
    monkeypatch.setattr(
        dependencies,
        "check_data_dir",
        lambda: {"service": "lean_data_dir", "ok": True, "detail": "/data"},
    )
    monkeypatch.setattr(
        dependencies,
        "check_results_dir",
        lambda: {"service": "results_dir_writable", "ok": True, "detail": "/runs"},
    )
    for name in ("check_alert_channel", "check_paper_order_pipeline", "check_source_certifications"):
        service = {
            "check_alert_channel": "external_alert_channel",
            "check_paper_order_pipeline": "paper_order_pipeline_v2",
            "check_source_certifications": "source_certification",
        }[name]
        monkeypatch.setattr(
            dependencies,
            name,
            lambda service=service: {"service": service, "ok": True, "detail": {}},
        )

    result = dependencies.dependency_health()
    items = {item["service"]: item for item in result["dependencies"]}

    assert result["status"] == "ok"
    assert items["backtest_worker"]["ok"] is True
    assert items["docker"]["ok"] is True
    assert items["docker"]["detail"]["localDockerSocket"] is False
    assert items["lean_runner"]["detail"]["mode"] == "delegated_to_backtest_worker"


def test_scheduled_automation_without_alert_channel_is_degraded(monkeypatch):
    monkeypatch.setattr(dependencies, "SCHEDULED_AUTOMATION_ENABLED", True)
    monkeypatch.setattr(dependencies, "external_alert_channel_configured", lambda: False)

    result = dependencies.check_alert_channel()

    assert result["ok"] is False
    assert result["detail"]["reason"] == "scheduled_automation_requires_external_alert_channel"
