import json
from datetime import date, timedelta

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


def import_daily_bars(symbol="AAPL", asset_class="equity", market="usa", venue="usa"):
    from app.services.market_repository import upsert_market_daily_bars

    start = date(2024, 1, 1)
    rows = []
    for index in range(90):
        close = 100 + index
        rows.append(
            {
                "trade_date": (start + timedelta(days=index)).isoformat(),
                "open": close - 1,
                "high": close + 2,
                "low": close - 2,
                "close": close,
                "volume": 1000 + index,
            }
        )
    upsert_market_daily_bars(rows, symbol=symbol, asset_class=asset_class, market=market, venue=venue, source="fixture")


def sample_llm_response():
    content = {
        "summary": {"headline": "Trend remains constructive", "thesis": "Price and moving averages are rising.", "score": 78},
        "technical": {"trend": "up"},
        "risks": ["Volatility can expand."],
        "catalysts": ["Momentum persistence."],
        "evidence": [
            {"fact": "The 20-day return is positive.", "sourceKey": "technical"},
            {"fact": "Ninety daily bars are available.", "sourceKey": "data_quality"},
        ],
        "signal": {
            "stance": "bullish",
            "direction": "long",
            "intent": "enter",
            "targetExposure": 0.25,
            "confidence": 0.72,
            "score": 78,
            "horizon": "swing",
            "entryLow": 180,
            "entryHigh": 190,
            "stopLoss": 170,
            "targetPrice": 210,
            "invalidation": "Close below 170",
            "reason": "Positive trend",
        },
    }
    return {"choices": [{"message": {"content": json.dumps(content)}}]}


def configure_llm(monkeypatch):
    from app.services import insights

    monkeypatch.setattr(insights, "INSIGHTS_LLM_BASE_URL", "https://llm.invalid/v1")
    monkeypatch.setattr(insights, "INSIGHTS_LLM_API_KEY", "secret-value")
    monkeypatch.setattr(insights, "INSIGHTS_LLM_MODEL", "test-model")
    monkeypatch.setattr(insights, "_post_json", lambda _payload: sample_llm_response())
    return insights


def test_context_and_guardrails_cover_daily_data_and_spot_short_block(tmp_path, monkeypatch):
    configure_platform(tmp_path, monkeypatch)
    import_daily_bars()
    from app.services import insights

    context = insights.build_context({"symbol": "AAPL", "assetClass": "equity", "market": "usa", "venue": "usa", "lookbackBars": 90})
    assert context["price"]["barCount"] == 90
    assert context["dataQuality"]["level"] == "ok"
    assert context["technical"]["sma20"] is not None

    final, guardrail = insights.guard_signal(
        {"stance": "bearish", "direction": "short", "intent": "enter", "targetExposure": -0.5, "confidence": 0.8, "score": 20},
        context,
        [{"fact": "Price weakened.", "sourceKey": "price"}],
    )
    assert final["direction"] == "flat"
    assert final["targetExposure"] == 0
    assert "spot_short_exposure_blocked" in guardrail["violations"]


@pytest.mark.parametrize(
    ("symbol", "asset_class", "market", "venue"),
    [
        ("AAPL", "equity", "usa", "usa"),
        ("BTCUSDT", "crypto", "coinbase", "coinbase"),
        ("BTCUSDT", "crypto_future", "binance", "binance"),
        ("GC", "future", "comex", "comex"),
    ],
)
def test_context_supports_every_platform_asset_class(tmp_path, monkeypatch, symbol, asset_class, market, venue):
    configure_platform(tmp_path, monkeypatch)
    import_daily_bars(symbol, asset_class, market, venue)
    from app.services import insights

    context = insights.build_context(
        {"symbol": symbol, "assetClass": asset_class, "market": market, "venue": venue, "lookbackBars": 90}
    )

    assert context["instrument"]["assetClass"] == asset_class
    assert context["price"]["barCount"] == 90
    assert (context["derivative"] is not None) is (asset_class in {"future", "crypto_future"})


def test_insight_run_persists_structured_report_and_signal(tmp_path, monkeypatch):
    configure_platform(tmp_path, monkeypatch)
    import_daily_bars()
    insights = configure_llm(monkeypatch)
    from app.services.tasks import create_task

    report = insights.create_report({"symbol": "AAPL", "assetClass": "equity", "market": "usa", "venue": "usa", "lookbackBars": 90})
    task = create_task("insight", "Insight AAPL", {}, related_id=report["id"])
    insights.attach_task(report["id"], task["id"])

    result = insights.run_report(task["id"], report["id"])

    assert result["status"] == "success"
    assert result["report"]["summary"]["score"] == 78
    assert result["signal"]["finalSignal"]["actionable"] is True
    assert result["signal"]["guardrail"]["passed"] is True


def test_insight_can_be_explicitly_handed_to_compatible_paper_session(tmp_path, monkeypatch):
    configure_platform(tmp_path, monkeypatch)
    import_daily_bars()
    insights = configure_llm(monkeypatch)
    from app.services import paper
    from app.services.tasks import create_task

    report = insights.create_report({"symbol": "AAPL", "assetClass": "equity", "market": "usa", "venue": "usa", "lookbackBars": 90})
    task = create_task("insight", "Insight AAPL", {}, related_id=report["id"])
    insights.attach_task(report["id"], task["id"])
    insights.run_report(task["id"], report["id"])
    session = paper.create_session({"name": "US paper", "symbol": "AAPL", "assetClass": "equity", "market": "usa", "venue": "usa", "cash": 100000})

    handoff = insights.handoff_to_paper(report["id"], session["id"], 0.25)

    assert handoff["created"] is True
    assert handoff["paperSignal"]["side"] == "buy"
    assert handoff["paperSignal"]["source"] == f"insight:{report['id']}"
    assert insights.get_report(report["id"])["signal"]["status"] == "handed_off"


def test_capabilities_never_return_api_key(monkeypatch):
    insights = configure_llm(monkeypatch)

    payload = insights.capabilities()

    assert payload["configured"] is True
    assert payload["model"] == "test-model"
    assert "secret-value" not in json.dumps(payload)


def test_invalid_structured_llm_output_is_retried_then_rejected(monkeypatch):
    insights = configure_llm(monkeypatch)
    calls = []

    def invalid_response(_payload):
        calls.append(True)
        return {"choices": [{"message": {"content": json.dumps({"summary": {}})}}]}

    monkeypatch.setattr(insights, "_post_json", invalid_response)

    with pytest.raises(insights.InsightError, match="after two attempts"):
        insights.request_analysis({"instrument": {}, "price": {}, "technical": {}, "dataQuality": {}})
    assert len(calls) == 2


def test_kimi_request_uses_structured_non_thinking_mode(monkeypatch):
    insights = configure_llm(monkeypatch)
    payloads = []
    monkeypatch.setattr(insights, "INSIGHTS_LLM_PROVIDER", "kimi")

    def capture_payload(payload):
        payloads.append(payload)
        return sample_llm_response()

    monkeypatch.setattr(insights, "_post_json", capture_payload)

    insights.request_analysis({"instrument": {}, "price": {}, "technical": {}, "dataQuality": {}})

    assert payloads[0]["thinking"] == {"type": "disabled"}
    assert payloads[0]["response_format"] == {"type": "json_object"}
    assert "temperature" not in payloads[0]


def test_insights_api_is_opt_in_and_queues_configured_requests(tmp_path, monkeypatch):
    configure_platform(tmp_path, monkeypatch)
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services import insights
    import app.api.insights as insights_api

    client = TestClient(app)
    monkeypatch.setattr(insights, "INSIGHTS_LLM_BASE_URL", "")
    monkeypatch.setattr(insights, "INSIGHTS_LLM_API_KEY", "")
    monkeypatch.setattr(insights, "INSIGHTS_LLM_MODEL", "")
    unavailable = client.post("/api/insights", json={"symbol": "AAPL", "assetClass": "equity", "market": "usa"})
    assert unavailable.status_code == 503

    configure_llm(monkeypatch)
    monkeypatch.setattr(insights_api, "dispatch_task", lambda _signature, task_id: task_id)
    accepted = client.post("/api/insights", json={"symbol": "AAPL", "assetClass": "equity", "market": "usa", "venue": "usa"})
    assert accepted.status_code == 202
    payload = accepted.json()
    assert payload["status"] == "queued"
    assert client.get(f"/api/insights/{payload['id']}").json()["task_id"] == payload["taskId"]


def test_cancelling_insight_task_updates_linked_report(tmp_path, monkeypatch):
    configure_platform(tmp_path, monkeypatch)
    insights = configure_llm(monkeypatch)
    from app.services.tasks import cancel_task, create_task

    report = insights.create_report({"symbol": "AAPL", "assetClass": "equity", "market": "usa", "venue": "usa"})
    task = create_task("insight", "Insight AAPL", {}, related_id=report["id"])
    insights.attach_task(report["id"], task["id"])

    cancelled = cancel_task(task["id"])

    assert cancelled["status"] == "cancelled"
    assert insights.get_report(report["id"])["status"] == "cancelled"
