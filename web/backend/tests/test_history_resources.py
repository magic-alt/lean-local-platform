from __future__ import annotations

import pytest


def _init_db():
    import app.db as db_module

    db_module.init_db()
    return db_module


def test_delete_backtest_removes_only_managed_run_directory(tmp_path, monkeypatch):
    db_module = _init_db()
    import app.services.history_resources as history

    runs_root = tmp_path / "runs"
    reports_root = tmp_path / "reports"
    result_dir = runs_root / "run-1" / "results"
    sibling = runs_root / "keep-me"
    result_dir.mkdir(parents=True)
    sibling.mkdir(parents=True)
    (result_dir / "result.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(history, "RUNS_DIR", runs_root)
    monkeypatch.setattr(history, "REPORTS_DIR", reports_root)

    with db_module.db() as connection:
        connection.execute(
            """
            insert into backtest_runs
                (id, symbol, asset_class, resolution, data_type, parameters_json, status,
                 docker_image, results_dir, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("run-1", "000001", "equity", "daily", "trade", "{}", "success", "lean:test", str(result_dir), "2026-07-21T00:00:00+00:00"),
        )

    result = history.delete_backtest("run-1")

    assert result["deleted"] is True
    assert not (runs_root / "run-1").exists()
    assert sibling.exists()
    with db_module.db() as connection:
        assert connection.execute("select count(*) as count from backtest_runs where id = ?", ("run-1",)).fetchone()["count"] == 0


def test_active_resources_cannot_be_deleted(tmp_path, monkeypatch):
    db_module = _init_db()
    import app.services.history_resources as history

    monkeypatch.setattr(history, "RUNS_DIR", tmp_path / "runs")
    with db_module.db() as connection:
        connection.execute(
            """
            insert into optimization_runs
                (id, project_id, status, parameters_json, results_dir, created_at)
            values (?, ?, ?, ?, ?, ?)
            """,
            ("opt-1", "project-1", "running", "{}", str(tmp_path / "runs" / "opt-1"), "2026-07-21T00:00:00+00:00"),
        )

    with pytest.raises(ValueError, match="Active optimizations"):
        history.delete_optimization("opt-1")

    with db_module.db() as connection:
        assert connection.execute("select count(*) as count from optimization_runs where id = ?", ("opt-1",)).fetchone()["count"] == 1


def test_global_history_clear_requires_typed_confirmation():
    _init_db()
    from app.services.maintenance import clear_local_history

    result = clear_local_history(dry_run=False, force=True)

    assert result["status"] == "blocked"
    assert "confirmation" in result["message"].lower()
