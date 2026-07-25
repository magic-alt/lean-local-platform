import pytest

from app.services import experiment_batches


def _item(item_id: str, fast: int, slow: int, sharpe: float, phase: str = "full"):
    return {
        "id": item_id,
        "related_id": f"run-{item_id}",
        "project_id": "project-1",
        "symbol": "000001",
        "status": "success",
        "parameters": {
            "parameters": {
                "optimizationCandidateKey": f"{fast}-{slow}",
                "optimizationOverrides": {"fast": fast, "slow": slow},
                "experimentFold": 1,
                "experimentPhase": phase,
            }
        },
        "result": {
            "statistics": {
                "Sharpe Ratio": str(sharpe),
                "Net Profit": "12.5%",
                "Drawdown": "8.0%",
                "Total Trades": "15",
            }
        },
        "error": None,
    }


def test_summary_builds_parameter_sensitivity_heatmap():
    summary = experiment_batches._summary(
        [
            _item("1", 5, 20, 0.5),
            _item("2", 5, 40, 0.8),
            _item("3", 10, 20, 1.1),
            _item("4", 10, 40, 1.4),
        ]
    )

    sensitivity = summary["parameterSensitivity"][0]
    assert sensitivity["xParameter"] == "fast"
    assert sensitivity["yParameter"] == "slow"
    assert sensitivity["xValues"] == [5.0, 10.0]
    assert len(sensitivity["cells"]) == 4


def test_compare_batches_ranks_on_median_metric(monkeypatch):
    batches = {
        "a": {
            "id": "a",
            "name": "A",
            "kind": "optimization",
            "mode": "single_symbol_grid",
            "status": "success",
            "created_at": "2026-01-01",
            "summary": experiment_batches._summary([_item("a1", 5, 20, 0.5), _item("a2", 10, 40, 0.7)]),
        },
        "b": {
            "id": "b",
            "name": "B",
            "kind": "optimization",
            "mode": "single_symbol_grid",
            "status": "success",
            "created_at": "2026-01-02",
            "summary": experiment_batches._summary([_item("b1", 5, 20, 1.2), _item("b2", 10, 40, 1.4)]),
        },
    }
    monkeypatch.setattr(experiment_batches, "detail", lambda batch_id: batches[batch_id])

    result = experiment_batches.compare_batches(["a", "b"])

    assert [item["id"] for item in result["batches"]] == ["b", "a"]
    assert result["batches"][0]["rank"] == 1
    assert result["batches"][0]["rankingValue"] == pytest.approx(1.3)
