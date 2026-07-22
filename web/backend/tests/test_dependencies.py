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

    result = dependencies.dependency_health()
    items = {item["service"]: item for item in result["dependencies"]}

    assert result["status"] == "ok"
    assert items["backtest_worker"]["ok"] is True
    assert items["docker"]["ok"] is True
    assert items["docker"]["detail"]["localDockerSocket"] is False
    assert items["lean_runner"]["detail"]["mode"] == "delegated_to_backtest_worker"
