from datetime import date, timedelta
from contextlib import contextmanager

import pytest


def configure_platform(tmp_path, monkeypatch):
    import app.db as db_module
    import app.services.tasks as task_service

    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(db_module, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(db_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(db_module, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(db_module, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(db_module, "RESEARCH_DIR", tmp_path / "research")
    monkeypatch.setattr(db_module, "OBJECT_STORE_DIR", tmp_path / "object-store")
    monkeypatch.setattr(db_module, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(task_service, "RUNS_DIR", tmp_path / "runs")
    db_module.init_db()


def sample_rows(count=130, end=date(2026, 7, 14), rising=True):
    dates = []
    cursor = end
    while len(dates) < count:
        if cursor.weekday() < 5:
            dates.append(cursor)
        cursor -= timedelta(days=1)
    dates.reverse()
    rows = []
    for index, trade_date in enumerate(dates):
        close = 50 + index * 0.1 if rising else 70 - index * 0.1
        rows.append({
            "date": trade_date.isoformat(), "open": close - 0.2, "high": close + 0.5,
            "low": close - 0.5, "close": close, "prev_close": close - (0.1 if rising else -0.1),
            "volume": 1_000_000 + index * 100, "amount": (1_000_000 + index * 100) * close,
            "turnover_rate": 2.0, "turnover_history_complete": True,
            "adj_factor": 1 + index * 0.001, "adj_factor_verified": True,
        })
    return rows


def test_qfq_and_indicator_formulas_are_based_on_120_plus_daily_bars():
    from app.services.ashare_tech_insights import calculate_metrics, qfq_rows

    raw = sample_rows()
    adjusted = qfq_rows(raw)
    latest_factor = raw[-1]["adj_factor"]
    assert adjusted[0]["close"] == pytest.approx(raw[0]["close"] * raw[0]["adj_factor"] / latest_factor)
    assert adjusted[-1]["close"] == pytest.approx(raw[-1]["close"])
    assert adjusted[-1]["volume"] == raw[-1]["volume"]
    metrics = calculate_metrics(adjusted)

    assert metrics["sampleCount"] == 130
    assert metrics["ma5"] == pytest.approx(sum(row["close"] for row in adjusted[-5:]) / 5, abs=1e-4)
    assert metrics["volumeRatio20"] == pytest.approx(
        adjusted[-1]["volume"] / (sum(row["volume"] for row in adjusted[-20:]) / 20), abs=1e-4
    )
    assert metrics["amountRatio20"] == pytest.approx(
        adjusted[-1]["amount"] / (sum(row["amount"] for row in adjusted[-20:]) / 20), abs=1e-4
    )
    assert metrics["ma120"] is not None
    assert metrics["dif"] is not None and metrics["dea"] is not None and metrics["macdHistogram"] is not None


def test_sample_gates_and_risk_evidence_block_low_buy():
    from app.services.ashare_tech_insights import calculate_metrics, classify_stock, qfq_rows

    short_rows = qfq_rows(sample_rows(count=19))
    short_metrics = calculate_metrics(short_rows)
    assert short_metrics["ma20"] is None
    assert "不足20日，禁止低吸筛选" in short_metrics["missing"]
    assert classify_stock(short_rows, short_metrics)["conclusion"] == "继续等待"

    rows = qfq_rows(sample_rows())
    metrics = calculate_metrics(rows)
    metrics.update({"ma20": metrics["close"], "ma60": metrics["close"] * 0.99, "drawdown20Pct": -10.0, "volumeRatio20": 0.65, "amountRatio20": 0.7})
    rows[-1]["low"] = rows[-2]["low"]
    normal = classify_stock(rows, metrics, code="002475")
    blocked = classify_stock(rows, metrics, code="002475", negative_announcement=True)
    assert normal["conclusion"] in {"低吸观察", "小仓试错前置", "重点观察"}
    assert blocked["conclusion"] == "风险较高"

    strong_metrics = {**metrics, "drawdown20Pct": -5.0}
    assert classify_stock(rows, strong_metrics, rule_tags=["strong_ai"])["conclusion"] == "不追高"
    storage = classify_stock(rows, metrics, rule_tags=["storage"], storage_sector_pullback_days=0)
    assert storage["conclusion"] == "继续等待"


def test_explicit_observation_pool_contains_exactly_the_26_requested_codes():
    from app.services.ashare_tech_insights import STOCK_POOL

    codes = {item["code"] for item in STOCK_POOL}
    assert len(codes) == 26
    assert {"002475", "688123", "688256", "600183"} <= codes


class FakeAdapter:
    def trade_calendar(self, _start, end):
        requested = date.fromisoformat(end)
        return [{"trade_date": end, "is_open": requested.weekday() < 5}]

    def daily_rows(self, _code, _start, end):
        return sample_rows(end=date.fromisoformat(end))

    def daily_basic_rows(self, _code, _start, end):
        return [{"trade_date": row["date"], "factors": {"turnover_rate": 2.0}} for row in sample_rows(end=date.fromisoformat(end))]

    def index_daily_rows(self, _code, _start, end):
        return sample_rows(end=date.fromisoformat(end))


class FakeValidationAdapter:
    def stock_by_code(self, code):
        return {"symbol": code, "name": "测试科技", "status": "listed", "source": "fixture"}


def test_full_run_persists_all_26_stocks_and_source_metadata(tmp_path, monkeypatch):
    configure_platform(tmp_path, monkeypatch)
    from app.services import ashare_tech_insights as service
    from app.services.tasks import create_task

    report = service.create_report("2026-07-14")
    task = create_task("ashare_tech_report", "fixture", {}, related_id=report["id"])
    service.attach_task(report["id"], task["id"])
    result = service.run_report(
        task["id"], report["id"], adapter=FakeAdapter(),
        cross_checker=lambda _code: {"close": sample_rows()[-1]["close"], "timestamp": "2026-07-14T15:00:00", "source": "fixture"},
        announcement_fetcher=lambda _code, _start, _end: [],
        policy_fetcher=lambda _start, _end: [],
    )

    assert result["status"] == "success"
    assert result["analysis_date"] == "2026-07-14"
    assert len(result["report"]["fullPool"]) == 26
    assert result["report"]["primarySource"].startswith("TuShare Pro")
    assert result["report"]["disclaimer"].startswith("仅用于研究")
    assert result["dataCompleteness"]["fullPoolDateAligned"] is True


def test_specialized_api_route_precedes_generic_dynamic_route(tmp_path, monkeypatch):
    configure_platform(tmp_path, monkeypatch)
    from fastapi.testclient import TestClient
    from app.main import app
    import app.api.ashare_tech_insights as api_module

    monkeypatch.setattr(api_module, "dispatch_task", lambda _signature, task_id: task_id)
    client = TestClient(app)
    capabilities = client.get("/api/ashare-tech-insights/capabilities")
    assert capabilities.status_code == 200
    assert capabilities.json()["poolSize"] == 26
    accepted = client.post("/api/ashare-tech-insights/reports", json={"requestedDate": "2026-07-14"})
    assert accepted.status_code == 202
    detail = client.get(f"/api/ashare-tech-insights/reports/{accepted.json()['id']}")
    assert detail.status_code == 200
    assert detail.json()["requested_date"] == "2026-07-14"
    assert client.get("/api/insights/ashare-tech/capabilities").status_code == 200


def test_watchlist_defaults_adds_updates_deletes_and_resets(tmp_path, monkeypatch):
    configure_platform(tmp_path, monkeypatch)
    from app.services import ashare_tech_insights as service

    default = service.get_watchlist()
    assert default["count"] == default["enabledCount"] == 26
    assert default["maxSize"] == 60

    added = service.add_watchlist_item(
        "603019", "ai_compute", ["strong_ai"], adapter=FakeValidationAdapter()
    )
    assert added["name"] == "测试科技"
    assert added["ruleTags"] == ["strong_ai"]
    with pytest.raises(service.AshareTechReportError, match="已在观察池"):
        service.add_watchlist_item("603019", "ai_compute", [], adapter=FakeValidationAdapter())

    disabled = service.update_watchlist_item("603019", enabled=False, rule_tags=["storage"])
    assert disabled["enabled"] is False
    assert disabled["ruleTags"] == ["storage"]
    deleted = service.delete_watchlist_item("603019")
    assert deleted["deleted"] is True
    assert deleted["watchlist"]["count"] == 26

    service.update_watchlist_item("002475", enabled=False)
    reset = service.reset_watchlist()
    assert reset["count"] == reset["enabledCount"] == 26
    assert next(item for item in reset["items"] if item["code"] == "300308")["ruleTags"] == ["strong_ai"]


def test_report_pool_snapshot_is_immutable_after_watchlist_edit(tmp_path, monkeypatch):
    configure_platform(tmp_path, monkeypatch)
    from app.services import ashare_tech_insights as service

    report = service.create_report("2026-07-14")
    before = report["poolSnapshot"]
    service.update_watchlist_item("002475", enabled=False)
    service.add_watchlist_item("603019", "ai_compute", ["strong_ai"], adapter=FakeValidationAdapter())

    unchanged = service.get_report(report["id"])
    assert unchanged["poolSnapshot"] == before
    assert unchanged["poolSnapshot"]["count"] == 26
    assert unchanged["pool_fingerprint"] == before["fingerprint"]

    forced = service.create_report("2026-07-14", force=True)
    assert forced["poolSnapshot"]["count"] == 26
    assert forced["pool_fingerprint"] != before["fingerprint"]


def test_watchlist_never_allows_zero_enabled_symbols(tmp_path, monkeypatch):
    configure_platform(tmp_path, monkeypatch)
    from app.services import ashare_tech_insights as service

    items = service.get_watchlist()["items"]
    for item in items[1:]:
        service.update_watchlist_item(item["code"], enabled=False)
    with pytest.raises(service.AshareTechReportError, match="至少需要保留1只"):
        service.update_watchlist_item(items[0]["code"], enabled=False)
    with pytest.raises(service.AshareTechReportError, match="最后1只"):
        service.delete_watchlist_item(items[0]["code"])


def test_watchlist_count_queries_support_mysql_dict_rows(monkeypatch):
    from app.services import ashare_tech_insights as service

    class Result:
        @staticmethod
        def fetchone():
            return {"count": 1}

        @staticmethod
        def fetchall():
            return []

    class Connection:
        @staticmethod
        def execute(sql, _params=None):
            assert "ashare_tech" in sql.lower()
            return Result()

    @contextmanager
    def mapping_db():
        yield Connection()

    monkeypatch.setattr(service, "db", mapping_db)
    service._ensure_default_watchlist()
    assert service.list_reports()["count"] == 1


def test_watchlist_api_validates_and_manages_items(tmp_path, monkeypatch):
    configure_platform(tmp_path, monkeypatch)
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services import ashare_tech_insights as service

    monkeypatch.setattr(service, "TushareAdapter", lambda: FakeValidationAdapter())
    client = TestClient(app)
    assert client.get("/api/ashare-tech-insights/watchlist").json()["count"] == 26
    added = client.post("/api/ashare-tech-insights/watchlist/items", json={
        "code": "603019", "groupKey": "ai_compute", "ruleTags": ["strong_ai"]
    })
    assert added.status_code == 201
    changed = client.patch("/api/ashare-tech-insights/watchlist/items/603019", json={"enabled": False, "ruleTags": ["storage"]})
    assert changed.status_code == 200
    assert changed.json()["ruleTags"] == ["storage"]
    removed = client.delete("/api/ashare-tech-insights/watchlist/items/603019")
    assert removed.status_code == 200
    assert client.post("/api/ashare-tech-insights/watchlist/reset").json()["count"] == 26


def test_ashare_tech_history_report_delete_cleans_task_and_blocks_active_report(tmp_path, monkeypatch):
    configure_platform(tmp_path, monkeypatch)
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db import db
    from app.services import ashare_tech_insights as service
    from app.services.tasks import create_task, update_task

    report = service.create_report("2026-07-14")
    task = create_task("ashare_tech_report", "A股科技股日报", {}, related_id=report["id"])
    service.attach_task(report["id"], task["id"])
    client = TestClient(app)

    assert client.delete(f"/api/ashare-tech-insights/reports/{report['id']}").status_code == 409

    service.fail_report(report["id"], "fixture complete")
    update_task(task["id"], status="failed", finished_at="2026-07-14T10:00:00+00:00")
    deleted = client.delete(f"/api/ashare-tech-insights/reports/{report['id']}")

    assert deleted.status_code == 200
    assert deleted.json()["deletedTasks"] == 1
    assert client.get(f"/api/ashare-tech-insights/reports/{report['id']}").status_code == 404
    with db() as connection:
        assert connection.execute("select count(*) as count from tasks where related_id = ?", (report["id"],)).fetchone()["count"] == 0
