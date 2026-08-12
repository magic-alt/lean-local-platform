from app.services import dependencies


def test_mysql_readiness_counts_use_information_schema_estimates(monkeypatch):
    statements = []

    class Connection:
        def execute(self, sql, parameters=None):
            statements.append((" ".join(sql.split()), parameters))
            return self

        def fetchall(self):
            return [{"readiness_table_name": "market_daily_bars", "readiness_table_rows": 4_000_000}]

    monkeypatch.setattr(dependencies, "database_backend", lambda: "mysql")

    counts, source = dependencies._database_table_counts(Connection(), ["market_daily_bars"])

    assert counts == {"market_daily_bars": 4_000_000}
    assert source == "information_schema_estimate"
    assert "count(*)" not in statements[0][0].lower()
    assert "table_name as readiness_table_name" in statements[0][0].lower()


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


def test_delegated_runner_checks_preserve_worker_failure_without_crashing():
    checks = dependencies._delegated_runner_checks(
        {
            "service": "backtest_worker",
            "ok": False,
            "detail": "celery ping timed out",
        }
    )

    assert all(item["ok"] is False for item in checks)
    assert all(item["detail"]["workers"] == [] for item in checks)
    assert all(item["detail"]["workerError"] == "celery ping timed out" for item in checks)


def test_scheduled_automation_without_alert_channel_is_degraded(monkeypatch):
    monkeypatch.setattr(dependencies, "SCHEDULED_AUTOMATION_ENABLED", True)
    monkeypatch.setattr(dependencies, "external_alert_channel_configured", lambda: False)

    result = dependencies.check_alert_channel()

    assert result["ok"] is False
    assert result["detail"]["reason"] == "scheduled_automation_requires_external_alert_channel"


def test_failed_alert_delivery_degrades_dependency_health(monkeypatch):
    monkeypatch.setattr(dependencies, "SCHEDULED_AUTOMATION_ENABLED", True)
    monkeypatch.setattr(dependencies, "external_alert_channel_configured", lambda: True)
    monkeypatch.setattr(
        dependencies,
        "notification_delivery_health",
        lambda: {
            "ok": False,
            "status": "degraded",
            "reason": "notification_delivery_failed",
        },
    )

    result = dependencies.check_alert_channel()

    assert result["ok"] is False
    assert result["detail"]["reason"] == "notification_delivery_failed"


def test_missing_alert_channel_does_not_degrade_interactive_execution():
    checks = [
        {"service": "database", "ok": True},
        {"service": "redis", "ok": True},
        {"service": "external_alert_channel", "ok": False},
    ]

    assert (
        dependencies._dependency_status(
            checks,
            dependencies.OPERATIONAL_CRITICAL_SERVICES,
        )
        == "degraded"
    )
    assert (
        dependencies._dependency_status(
            checks,
            dependencies.EXECUTION_CRITICAL_SERVICES,
        )
        == "ok"
    )
    assert dependencies._dependency_blockers(
        checks,
        dependencies.OPERATIONAL_CRITICAL_SERVICES,
    ) == ["external_alert_channel"]
    assert dependencies._dependency_blockers(
        checks,
        dependencies.EXECUTION_CRITICAL_SERVICES,
    ) == []


def test_source_certification_is_reported_as_the_exact_execution_blocker():
    checks = [
        {"service": "database", "ok": True},
        {"service": "redis", "ok": True},
        {"service": "source_certification", "ok": False},
        {"service": "external_alert_channel", "ok": False},
    ]

    assert dependencies._dependency_blockers(
        checks,
        dependencies.EXECUTION_CRITICAL_SERVICES,
    ) == ["source_certification"]
    assert dependencies._dependency_blockers(
        checks,
        dependencies.OPERATIONAL_CRITICAL_SERVICES,
    ) == ["source_certification", "external_alert_channel"]
