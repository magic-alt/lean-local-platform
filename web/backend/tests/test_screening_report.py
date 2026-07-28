import json


def test_screening_markers_become_structured_artifact_and_html_section(tmp_path):
    from app.lean_engine.screening import extract_screening_report
    from app.reporting.html_report import render_report_file

    results = tmp_path / "results"
    results.mkdir()
    summary = {
        "schemaVersion": 1,
        "asOfDate": "2026-07-24",
        "universeCode": "CSI300",
        "evaluated": 2,
        "qualified": 1,
        "selected": ["600519"],
    }
    items = [
        {
            "symbol": "600519",
            "trend": "持续上涨",
            "technicalScore": 90,
            "fundamentalScore": 80,
            "overallScore": 86,
            "suitableToBuy": True,
            "fundamentals": {"roe": 28.0, "pe": 24.0},
            "reasons": ["均线多头", "ROE达标"],
            "risks": [],
        },
        {
            "symbol": "000001",
            "trend": "横盘震荡",
            "technicalScore": 45,
            "fundamentalScore": 50,
            "overallScore": 47,
            "suitableToBuy": False,
            "fundamentals": {},
            "reasons": [],
            "risks": ["基本面字段覆盖不足"],
        },
    ]
    lines = [f"2026-07-24 TRACE:: LEAN_SCREENING_SUMMARY|{json.dumps(summary, ensure_ascii=False)}"]
    lines.extend(f"TRACE:: LEAN_SCREENING|{json.dumps(item, ensure_ascii=False)}" for item in items)
    (results / "log.txt").write_text("\n".join(lines), encoding="utf-8")

    artifact = extract_screening_report(results)

    assert artifact == results / "screening-report.json"
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["summary"]["selected"] == ["600519"]
    assert [item["symbol"] for item in payload["selected"]] == ["600519"]

    result_path = results / "run.json"
    result_path.write_text(
        json.dumps(
            {
                "algorithmConfiguration": {
                    "name": "A股指数技术面与基本面选股",
                    "parameters": {"ticker": "000001", "market": "china"},
                },
                "statistics": {},
                "charts": {},
                "orders": {},
            }
        ),
        encoding="utf-8",
    )
    report_path = results / "report.html"
    render_report_file(result_path, report_path)
    html = report_path.read_text(encoding="utf-8")
    assert "指数成分股技术面与基本面筛选" in html
    assert "600519" in html
    assert "基本面字段覆盖不足" in html
