from pathlib import Path

from fastapi.testclient import TestClient


def test_run_file_resolves_host_path_inside_container_workspace(tmp_path, monkeypatch):
    from app.core import config
    from app.services.run_paths import run_file

    run_id = "600460-20240101-20260713-20260716235348"
    runs_dir = tmp_path / "web" / "runtime" / "runs"
    expected = runs_dir / run_id / "results" / f"{run_id}.json"
    expected.parent.mkdir(parents=True)
    expected.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(config, "RUNS_DIR", runs_dir)

    resolved = run_file(
        run_id,
        f"/Users/example/lean-platform/web/runtime/runs/{run_id}/results/{run_id}.json",
        f"results/{run_id}.json",
    )

    assert resolved == expected


def test_run_directory_resolves_workspace_path_on_host(tmp_path, monkeypatch):
    from app.core import config
    from app.services.run_paths import run_directory

    run_id = "run-1"
    runs_dir = tmp_path / "web" / "runtime" / "runs"
    expected = runs_dir / run_id / "results"
    expected.mkdir(parents=True)
    monkeypatch.setattr(config, "RUNS_DIR", runs_dir)

    resolved = run_directory(run_id, f"/workspace/web/runtime/runs/{run_id}/results", relative="results")

    assert resolved == expected


def test_chart_endpoint_resolves_result_path_from_another_runtime_root(tmp_path, monkeypatch):
    from app.api import backtests as backtests_api
    from app.core import config
    from app.main import app

    run_id = "portable-run"
    runs_dir = tmp_path / "web" / "runtime" / "runs"
    results_dir = runs_dir / run_id / "results"
    results_dir.mkdir(parents=True)
    result_path = results_dir / f"{run_id}.json"
    result_path.write_text('{"charts": {}, "statistics": {}, "orders": {}}', encoding="utf-8")
    monkeypatch.setattr(config, "RUNS_DIR", runs_dir)
    monkeypatch.setattr(
        backtests_api,
        "get_backtest",
        lambda requested: {
            "id": requested,
            "status": "success",
            "symbol": None,
            "parameters": {},
            "results_dir": f"/workspace/web/runtime/runs/{run_id}/results",
            "result_json_path": f"/workspace/web/runtime/runs/{run_id}/results/{run_id}.json",
        },
    )

    response = TestClient(app).get(f"/api/backtests/{run_id}/chart-data")

    assert response.status_code == 200
    assert response.json()["series"]["equity"] == []


def test_screening_endpoint_reads_legacy_artifact_and_enriches_identity(tmp_path, monkeypatch):
    from app.api import backtests as backtests_api
    from app.core import config
    from app.main import app
    from app.services import screening_results

    run_id = "legacy-screening"
    runs_dir = tmp_path / "web" / "runtime" / "runs"
    results_dir = runs_dir / run_id / "results"
    results_dir.mkdir(parents=True)
    (results_dir / "screening-report.json").write_text(
        """
        {
          "schemaVersion": 1,
          "asOfDate": "2026-07-22",
          "universeCode": "CSI300",
          "summary": {"selected": ["792"]},
          "items": [
            {"symbol": "792", "overallScore": 88, "suitableToBuy": true}
          ]
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "RUNS_DIR", runs_dir)
    monkeypatch.setattr(
        backtests_api,
        "get_backtest",
        lambda requested: {
            "id": requested,
            "status": "success",
            "parameters": {
                "market": "china",
                "strategyTemplateKey": "ashare_index_screening",
            },
            "results_dir": f"/workspace/web/runtime/runs/{run_id}/results",
        },
    )
    monkeypatch.setattr(
        screening_results,
        "resolve_security_identities",
        lambda symbols, **kwargs: {
            "000792": {
                "symbol": "000792",
                "name": "盐湖股份",
                "display": "000792 盐湖股份",
            }
        },
    )

    response = TestClient(app).get(f"/api/backtests/{run_id}/screening")

    assert response.status_code == 200
    assert response.json()["schemaVersion"] == 2
    assert response.json()["items"][0]["symbol"] == "000792"
    assert response.json()["items"][0]["name"] == "盐湖股份"
    assert response.json()["summary"]["selected"] == ["000792"]
