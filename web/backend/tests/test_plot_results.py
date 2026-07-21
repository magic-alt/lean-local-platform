import json

from app.reporting.html_report import REPORT_LAYOUT_VERSION, build_report


def test_report_file_responses_disable_browser_caching():
    from app.api.reports import REPORT_FILE_CACHE_HEADERS

    assert REPORT_FILE_CACHE_HEADERS["Cache-Control"] == "no-store, max-age=0"
    assert REPORT_FILE_CACHE_HEADERS["Pragma"] == "no-cache"


def test_report_header_structures_run_metadata_and_chart_names():
    result = {
        "algorithmConfiguration": {
            "name": "Local equity 01810 Backtest",
            "accountCurrency": "HKD",
            "startDate": "2024-01-01T00:00:00Z",
            "endDate": "2026-07-13T23:59:59Z",
            "parameters": {
                "ticker": "01810",
                "market": "hongkong",
                "providerSource": "akshare",
                "initialCash": "500000",
            },
        },
        "charts": {
            "Strategy Equity": {"series": {}},
            "Portfolio Turnover": {"series": {}},
        },
        "statistics": {},
    }
    source = "/workspace/web/runtime/runs/run-01810/results/run-01810.json"

    report = build_report(result, source)

    assert "Local equity 01810 Backtest" in report
    assert "运行编号" in report
    assert "run-01810" in report
    assert "回测标的" in report and "01810" in report
    assert "回测区间" in report and "2024-01-01" in report and "2026-07-13" in report
    assert "可用图表" in report
    assert '<li class="chart-chip">Strategy Equity</li>' in report
    assert '<li class="chart-chip">Portfolio Turnover</li>' in report
    assert "结果文件" in report and "运行环境路径" in report
    assert "Generated from" not in report
    assert "Charts available:" not in report
    assert f'data-report-layout="{REPORT_LAYOUT_VERSION}"' in report
    assert f'<meta name="report-layout" content="{REPORT_LAYOUT_VERSION}">' in report


def test_report_regeneration_discovers_main_result_and_uses_canonical_layout(tmp_path):
    from scripts.regenerate_backtest_reports import discover_targets, regenerate

    run_id = "600519-20240101-20241231-test"
    results = tmp_path / "web" / "runtime" / "runs" / run_id / "results"
    results.mkdir(parents=True)
    result_json = results / f"{run_id}.json"
    result_json.write_text(
        '{"algorithmConfiguration":{"name":"Local equity 600519 Backtest","parameters":{"ticker":"600519"}},"charts":{},"statistics":{}}',
        encoding="utf-8",
    )
    (results / f"{run_id}-summary.json").write_text("{}", encoding="utf-8")
    report = results / "report.html"
    report.write_text("<html>old header</html>", encoding="utf-8")
    manifest = results / "artifact-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "runId": run_id,
                "artifacts": [
                    {
                        "name": "report.html",
                        "kind": "lean-output",
                        "relativePath": "results/report.html",
                        "size": report.stat().st_size,
                        "mtime": report.stat().st_mtime,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    targets = discover_targets(tmp_path)
    assert len(targets) == 1
    assert targets[0].result_json == result_json

    regenerate(targets[0])

    rendered = report.read_text(encoding="utf-8")
    assert "Local equity 600519 Backtest" in rendered
    assert f'data-report-layout="{REPORT_LAYOUT_VERSION}"' in rendered
    assert "old header" not in rendered
    refreshed_manifest = json.loads(manifest.read_text(encoding="utf-8"))
    assert refreshed_manifest["reportLayout"] == REPORT_LAYOUT_VERSION
    assert refreshed_manifest["artifacts"][0]["layout"] == REPORT_LAYOUT_VERSION
    assert refreshed_manifest["artifacts"][0]["size"] == report.stat().st_size


def test_report_regeneration_prefers_named_demo_result_when_directory_has_other_results(tmp_path):
    from scripts.regenerate_backtest_reports import discover_targets

    results = tmp_path / "web" / "runtime" / "legacy" / "root-demo" / "results"
    results.mkdir(parents=True)
    expected = results / "docker-demo-backtest.json"
    expected.write_text("{}", encoding="utf-8")
    (results / "another-backtest.json").write_text("{}", encoding="utf-8")
    (results / "report.html").write_text("<html>old</html>", encoding="utf-8")

    targets = discover_targets(tmp_path)

    assert len(targets) == 1
    assert targets[0].result_json == expected


def test_markdown_report_uses_same_title_and_core_header_metadata():
    from app.services.report_export import markdown_report, report_payload

    payload = report_payload(
        {
            "id": "backtest:run-01810",
            "run_id": "run-01810",
            "status": "success",
            "symbol": "01810",
            "asset_class": "equity",
            "venue": "hongkong",
            "parameters": {
                "start": "2024-01-01",
                "end": "2026-07-13",
                "providerSource": "akshare",
                "cash": "500000",
            },
        }
    )
    report = markdown_report(payload)

    assert report.startswith("<!-- report-layout-v2 -->\n\n# Local equity 01810 Backtest")
    assert "运行编号 `run-01810`" in report
    assert "- Symbol: 01810" in report
    assert "- Market: hongkong" in report
    assert "- Provider: akshare" in report
