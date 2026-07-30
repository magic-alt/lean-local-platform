from __future__ import annotations

from datetime import date, timedelta


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


def sample_report():
    base = {
        "date": "2026-01-02",
        "close": 100.0,
        "changePct": 1.0,
        "ma5": 99.0,
        "ma10": 98.0,
        "ma20": 97.0,
        "ma60": 90.0,
        "ma120": 80.0,
        "ma20Direction": "向上",
        "ma60Direction": "向上",
        "macdStatus": "零轴上；无新交叉；柱体扩张",
        "return5Pct": 3.0,
        "return10Pct": 8.0,
        "volatility20": 0.02,
        "drawdown20Pct": -5.0,
        "volumeRatio20": 1.0,
        "amountRatio20": 1.0,
        "turnoverRate": 2.0,
        "priceStructure": "上升",
        "keySupport": 97.0,
        "invalidation": 94.0,
        "triggerType": "强趋势延续",
        "dataCompleteness": {"sampleCount": 130, "missing": [], "latestDate": "2026-01-02"},
        "announcements": [],
    }
    return {
        "title": "fixture",
        "requestedDate": "2026-01-02",
        "analysisDate": "2026-01-02",
        "sourceConflicts": [],
        "fullPool": [
            {
                **base,
                "code": "002475",
                "name": "立讯精密",
                "conclusion": "重点观察",
                "announcementRisk": "未发现重大负面",
            },
            {
                **base,
                "code": "688256",
                "name": "寒武纪",
                "conclusion": "风险较高",
                "announcementRisk": "存在重大负面关键词，否决低吸",
            },
        ],
        "marketEnvironment": [
            {"code": "399001", "name": "深证成指", "date": "2026-01-02", "changePct": 0.5, "source": "fixture"}
        ],
        "policyEvidence": [],
        "finalThreeLines": {"overallStage": "趋势延续"},
    }


def valid_requester(system, payload):
    symbols = payload["CONTEXT"]["symbols"]
    if "技术趋势" in system:
        return {
            "stocks": [{
                "symbol": symbol,
                "forecasts": [{
                    "horizonDays": horizon,
                    "direction": "bullish",
                    "probabilities": {"bullish": 0.7, "neutral": 0.2, "bearish": 0.1},
                    "trendScore": 80,
                    "rationale": "趋势向上",
                    "evidenceIds": [f"TECH-{symbol}"],
                    "invalidation": "跌破支撑",
                } for horizon in (1, 5, 20)],
                "candidateSignal": {
                    "stance": "bullish",
                    "direction": "long",
                    "intent": "enter",
                    "targetExposure": 0.1,
                    "confidence": 0.7,
                    "score": 80,
                    "horizon": "5d",
                    "entryLow": 99,
                    "entryHigh": 100,
                    "stopLoss": 94,
                    "targetPrice": 110,
                    "invalidation": "收盘跌破94",
                    "reason": "趋势向上且价格计划完整",
                    "evidenceIds": [f"TECH-{symbol}"],
                },
            } for symbol in symbols]
        }, {"total_tokens": 100}, 12
    if "PIT基本面" in system:
        return {
            "stocks": [{
                "symbol": symbol,
                "score": 60,
                "quality": "neutral",
                "coverage": 0,
                "summary": "覆盖不足",
                "catalysts": [],
                "risks": ["覆盖不足"],
                "evidenceIds": [f"FUND-{symbol}"],
            } for symbol in symbols]
        }, {"total_tokens": 80}, 10
    if "多头研究" in system or "空头研究" in system:
        return {
            "stocks": [{
                "symbol": symbol,
                "score": 60,
                "summary": "审阅完成",
                "arguments": ["结构化证据"],
                "evidenceIds": [f"TECH-{symbol}"],
            } for symbol in symbols]
        }, {"total_tokens": 60}, 8
    if "风险审查" in system:
        return {
            "stocks": [{
                "symbol": symbol,
                "score": 20,
                "status": "pass",
                "summary": "未发现风险",
                "risks": [],
                "evidenceIds": [f"TECH-{symbol}"],
            } for symbol in symbols]
        }, {"total_tokens": 50}, 7
    return {
        "marketRegime": "趋势延续",
        "summary": "优先跟踪规则与模型一致标的",
        "selections": [{
            "rank": index,
            "symbol": symbol,
            "consensusScore": 90 - index,
            "rationale": "多阶段共识",
            "evidenceIds": [f"TECH-{symbol}"],
        } for index, symbol in enumerate(symbols, 1)],
    }, {"total_tokens": 70}, 9


def _configured_agent(monkeypatch):
    from app.services import ashare_tech_agents as agents

    monkeypatch.setattr(agents, "INSIGHTS_LLM_API_KEY", "secret-key")
    monkeypatch.setattr(agents, "INSIGHTS_LLM_BASE_URL", "https://model.example/v1")
    monkeypatch.setattr(agents, "INSIGHTS_LLM_PROVIDER", "deepseek")
    monkeypatch.setattr(agents, "INSIGHTS_LLM_MODEL", "deepseek-v4-flash")
    return agents


def test_six_agent_pipeline_persists_predictions_and_enforces_hard_veto(tmp_path, monkeypatch):
    configure_platform(tmp_path, monkeypatch)
    agents = _configured_agent(monkeypatch)
    from app.services import ashare_tech_insights as reports
    from app.services.tasks import create_task

    report_row = reports.create_report("2026-01-02", analysis_mode="hybrid_multi_agent")
    task = create_task("ashare_tech_report", "fixture", {}, related_id=report_row["id"])
    result = agents.run_agent_pipeline(
        task_id=task["id"],
        report_id=report_row["id"],
        report=sample_report(),
        requester=valid_requester,
    )

    assert result["status"] == "success"
    assert len(result["stages"]) == 6
    assert [item["symbol"] for item in result["topSelections"]] == ["002475"]
    detail = agents.get_agent_run(result["runId"])
    assert len(detail["predictions"]) == 6
    assert {item["horizon_days"] for item in detail["predictions"]} == {1, 5, 20}
    assert all(item["model"] == "deepseek-v4-flash" for item in detail["predictions"])
    assert len(detail["candidateSignals"]) == 2
    assert len(detail["stockInsights"]) == 2
    signals = {item["symbol"]: item for item in detail["candidateSignals"]}
    assert signals["002475"]["finalSignal"]["targetExposure"] == 0.1
    assert signals["002475"]["finalSignal"]["actionable"] is True
    assert signals["688256"]["status"] == "veto"
    assert signals["688256"]["finalSignal"]["targetExposure"] == 0
    assert "risk_veto" in signals["688256"]["guardrail"]["violations"]
    assert all(stage["system_prompt"] for stage in detail["stages"])
    assert detail["promptSnapshot"]


def test_agent_failure_is_visible_and_uses_deterministic_fallback(tmp_path, monkeypatch):
    configure_platform(tmp_path, monkeypatch)
    agents = _configured_agent(monkeypatch)
    from app.services import ashare_tech_insights as reports
    from app.services.tasks import create_task

    report_row = reports.create_report("2026-01-02", analysis_mode="hybrid_multi_agent")
    task = create_task("ashare_tech_report", "fixture", {}, related_id=report_row["id"])

    def failing_requester(_system, _payload):
        raise TimeoutError("secret-key timed out")

    result = agents.run_agent_pipeline(
        task_id=task["id"],
        report_id=report_row["id"],
        report=sample_report(),
        requester=failing_requester,
    )

    assert result["status"] == "degraded"
    assert all(stage["status"] == "fallback" for stage in result["stages"])
    assert "secret-key" not in str(result)
    assert result["predictionCount"] == 0
    assert agents.get_agent_run(result["runId"])["predictions"] == []


def test_prompt_versions_are_immutable_and_production_profile_is_explicit(tmp_path, monkeypatch):
    configure_platform(tmp_path, monkeypatch)
    agents = _configured_agent(monkeypatch)
    prompts = agents.builtin_prompt_version()["stagePrompts"]

    first = agents.save_prompt_version(
        name="科技趋势模板",
        description="第一版",
        stage_prompts=prompts,
    )
    changed = {**prompts, "technical": prompts["technical"] + "\n优先检查 RSI 与区间位置。"}
    second = agents.save_prompt_version(
        name="科技趋势模板",
        description="第二版",
        template_key=first["templateKey"],
        stage_prompts=changed,
    )

    assert first["id"] != second["id"]
    assert (first["version"], second["version"]) == (1, 2)
    assert agents.get_prompt_version(first["id"])["stagePrompts"]["technical"] == prompts["technical"]
    versions = agents.list_prompt_templates(first["templateKey"])
    assert [item["version"] for item in versions["items"]] == [2, 1]

    profile = agents.set_production_profile("deepseek", "deepseek-v4-pro", second["id"])
    assert profile["provider"] == "deepseek"
    assert profile["model"] == "deepseek-v4-pro"
    assert profile["promptVersionId"] == second["id"]


def test_pit_context_excludes_future_financial_facts(tmp_path, monkeypatch):
    configure_platform(tmp_path, monkeypatch)
    from app.db import db, utc_now
    from app.services.ashare_tech_agents import build_fact_context

    with db() as connection:
        connection.execute(
            """
            insert into financial_facts
                (symbol,field_name,report_date,announce_date,effective_date,value,unit,source,created_at)
            values (?,?,?,?,?,?,?,?,?)
            """,
            ("002475", "roe", "2025-09-30", "2025-10-20", "2025-10-20", 0.2, "ratio", "fixture", utc_now()),
        )
        connection.execute(
            """
            insert into financial_facts
                (symbol,field_name,report_date,announce_date,effective_date,value,unit,source,created_at)
            values (?,?,?,?,?,?,?,?,?)
            """,
            ("002475", "roe", "2026-03-31", "2026-04-20", "2026-04-20", 0.9, "ratio", "future", utc_now()),
        )

    context = build_fact_context(sample_report())
    fact = next(item for item in context["facts"] if item["id"] == "FUND-002475")
    assert fact["metrics"]["roe"] == 0.2
    assert all(item["source"] != "future" for item in fact["evidence"])


class EvaluationAdapter:
    @staticmethod
    def _dates(start, end):
        cursor = date.fromisoformat(start)
        last = date.fromisoformat(end)
        output = []
        while cursor <= last:
            if cursor.weekday() < 5:
                output.append(cursor.isoformat())
            cursor += timedelta(days=1)
        return output

    def trade_calendar(self, start, end):
        return [{"trade_date": item, "is_open": True} for item in self._dates(start, end)]

    def daily_rows(self, _symbol, start, end):
        return [{
            "date": item,
            "open": 100 + index,
            "high": 101 + index,
            "low": 99 + index,
            "close": 100 + index,
            "prev_close": 99 + index,
            "volume": 1000,
            "amount": 100000,
            "adj_factor": 1.0,
        } for index, item in enumerate(self._dates(start, end))]

    def index_daily_rows(self, _symbol, start, end):
        return [{
            "date": item,
            "open": 100 + index * 0.2,
            "high": 101 + index * 0.2,
            "low": 99 + index * 0.2,
            "close": 100 + index * 0.2,
            "prev_close": 100 + max(0, index - 1) * 0.2,
            "volume": 1000,
            "amount": 100000,
            "adj_factor": 1.0,
        } for index, item in enumerate(self._dates(start, end))]


def test_prediction_evaluation_uses_exact_trading_horizons_and_is_idempotent(tmp_path, monkeypatch):
    configure_platform(tmp_path, monkeypatch)
    agents = _configured_agent(monkeypatch)
    from app.services import ashare_tech_insights as reports
    from app.services.tasks import create_task

    report_row = reports.create_report("2026-01-02", analysis_mode="hybrid_multi_agent")
    task = create_task("ashare_tech_report", "fixture", {}, related_id=report_row["id"])
    agents.run_agent_pipeline(
        task_id=task["id"],
        report_id=report_row["id"],
        report=sample_report(),
        requester=valid_requester,
    )

    first = agents.refresh_evaluations(adapter=EvaluationAdapter(), as_of_date="2026-02-20")
    second = agents.refresh_evaluations(adapter=EvaluationAdapter(), as_of_date="2026-02-20")
    summary = agents.evaluation_summary()

    assert first == {"evaluated": 6, "pending": 0, "failed": 0}
    assert second == {"evaluated": 0, "pending": 0, "failed": 0}
    assert summary["sampleSize"] == 6
    assert {item["horizonDays"] for item in summary["byHorizon"]} == {1, 5, 20}


def test_model_diagnostic_never_returns_api_key(monkeypatch):
    agents = _configured_agent(monkeypatch)
    result = agents.model_diagnostics(
        requester=lambda _system, _payload: ({"ok": True}, {"total_tokens": 2}, 4)
    )
    assert result["status"] == "ok"
    assert "secret-key" not in str(result)


def test_anthropic_messages_structured_content_is_supported():
    from app.services.ashare_tech_agents import _endpoint, _extract_content

    runtime = {
        "provider": "anthropic",
        "base_url": "https://api.anthropic.com/v1",
    }
    assert _endpoint(runtime) == "https://api.anthropic.com/v1/messages"
    assert _extract_content({
        "content": [{"type": "text", "text": '{"ok":true}'}],
    }) == {"ok": True}


def test_multiclass_brier_uses_standard_sum_over_classes():
    from app.services.ashare_tech_agents import _brier

    score = _brier({"bullish": 0.7, "neutral": 0.2, "bearish": 0.1}, "bullish")
    assert round(score, 8) == 0.14
