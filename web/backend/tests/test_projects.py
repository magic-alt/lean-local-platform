import json
from pathlib import Path

from fastapi.testclient import TestClient


def configure_temp_db(tmp_path, monkeypatch):
    import app.db as db_module
    import app.services.projects as projects_module

    monkeypatch.setattr(db_module, "DATABASE_URL", f"sqlite:///{tmp_path / 'test.sqlite3'}")
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(db_module, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(db_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(db_module, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(db_module, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(db_module, "RESEARCH_DIR", tmp_path / "research")
    monkeypatch.setattr(db_module, "OBJECT_STORE_DIR", tmp_path / "object-store")
    monkeypatch.setattr(db_module, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(projects_module, "PROJECTS_DIR", tmp_path / "projects")
    db_module.init_db()
    return db_module


def test_project_files_fallback_from_stale_host_path(tmp_path, monkeypatch):
    db_module = configure_temp_db(tmp_path, monkeypatch)
    from app.main import app

    project_id = "legacy-project"
    fallback = tmp_path / "projects" / project_id
    fallback.mkdir(parents=True)
    (fallback / "main.py").write_text("class LegacyAlgorithm: pass\n", encoding="utf-8")
    (fallback / "project.json").write_text(json.dumps({"mainFile": "main.py"}), encoding="utf-8")
    with db_module.db() as connection:
        connection.execute(
            """
            insert into projects
                (id, name, language, algorithm_class, project_path, main_file, config_json, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                "Legacy Project",
                "Python",
                "LegacyAlgorithm",
                "/Users/example/lean-platform/web/runtime/projects/legacy-project",
                "main.py",
                db_module.json_dump({"mainFile": "main.py"}),
                "2026-07-07T00:00:00+00:00",
                "2026-07-07T00:00:00+00:00",
            ),
        )

    client = TestClient(app)
    project = client.get(f"/api/projects/{project_id}")
    files = client.get(f"/api/projects/{project_id}/files")
    main_file = client.get(f"/api/projects/{project_id}/file", params={"path": "main.py"})

    assert project.status_code == 200
    assert project.json()["project_path"] == str(fallback)
    assert files.status_code == 200
    assert [item["path"] for item in files.json()] == ["main.py", "project.json"]
    assert main_file.status_code == 200
    assert main_file.json()["content"] == "class LegacyAlgorithm: pass\n"


def test_api_update_project_config(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)
    from app.main import app

    client = TestClient(app)
    created = client.post(
        "/api/projects",
        json={
            "name": "update-project",
            "language": "Python",
            "templateKey": "ema_cross",
            "assetClass": "equity",
            "market": "china",
            "venue": "china",
            "resolution": "daily",
            "dataType": "trade",
            "parameters": {"period": 20},
        },
    ).json()

    response = client.put(f"/api/projects/{created['id']}", json={"name": "update-project-v2", "config": {"symbol": "600460", "source": "tushare"}})
    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "update-project-v2"
    assert payload["config"]["symbol"] == "600460"
    assert payload["config"]["source"] == "tushare"
    assert payload["config"]["templateKey"] == "ema_cross"

    changed = client.put(
        f"/api/projects/{created['id']}",
        json={"config": {"templateKey": "rsi_reversion", "parameters": {"period": 14, "buyBelow": 30, "sellAbove": 55}}},
    ).json()
    source = (Path(changed["project_path"]) / "main.py").read_text(encoding="utf-8")
    assert changed["config"]["templateKey"] == "rsi_reversion"
    assert "self.rsi = self.rsi" in source
    assert "self.fast = self.ema" not in source


def test_api_clone_project_with_files(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)
    from app.main import app

    client = TestClient(app)
    created = client.post(
        "/api/projects",
        json={"name": "clone-source", "language": "Python", "templateKey": "ema_cross"},
    ).json()

    source_root = Path(created["project_path"])
    (source_root / "extra.txt").write_text("extra payload\n", encoding="utf-8")

    clone_response = client.post(
        f"/api/projects/{created['id']}/clone",
        json={"name": "clone-source-copy", "config": {"start": "2026-01-01", "symbol": "000001"}},
    )
    assert clone_response.status_code == 200
    cloned = clone_response.json()
    assert cloned["id"] != created["id"]
    assert cloned["name"] == "clone-source-copy"
    assert cloned["config"]["start"] == "2026-01-01"
    assert cloned["config"]["symbol"] == "000001"
    assert cloned["config"]["templateKey"] == "ema_cross"

    files = client.get(f"/api/projects/{cloned['id']}/files").json()
    file_names = {item["path"] for item in files}
    assert "main.py" in file_names
    assert "project.json" in file_names
    assert "extra.txt" in file_names
    assert (Path(cloned["project_path"]) / "project.json").read_text(encoding="utf-8").strip() != ""

    changed_clone = client.post(
        f"/api/projects/{created['id']}/clone",
        json={"name": "clone-rsi", "config": {"templateKey": "rsi_reversion"}},
    ).json()
    changed_source = (Path(changed_clone["project_path"]) / "main.py").read_text(encoding="utf-8")
    assert changed_clone["config"]["templateKey"] == "rsi_reversion"
    assert "self.rsi = self.rsi" in changed_source
    assert "self.fast = self.ema" not in changed_source


def test_delete_project_archives_source_and_preserves_completed_history(tmp_path, monkeypatch):
    db_module = configure_temp_db(tmp_path, monkeypatch)
    from app.main import app

    client = TestClient(app)
    project = client.post(
        "/api/projects",
        json={"name": "stale-project", "language": "Python", "templateKey": "ema_cross"},
    ).json()
    project_root = Path(project["project_path"])
    with db_module.db() as connection:
        connection.execute(
            """
            insert into tasks
                (id,kind,status,title,project_id,parameters_json,log_path,created_at,finished_at)
            values ('task-history','backtest','success','history',?,'{}',?,'2026-08-01','2026-08-01')
            """,
            (project["id"], str(tmp_path / "history.log")),
        )
        connection.execute(
            """
            insert into backtest_runs
                (id,task_id,project_id,symbol,parameters_json,status,docker_image,results_dir,created_at,finished_at)
            values ('run-history','task-history',?,'AAPL','{}','success','lean:test',?,'2026-08-01','2026-08-01')
            """,
            (project["id"], str(tmp_path / "runs" / "run-history" / "results")),
        )

    response = client.delete(f"/api/projects/{project['id']}")

    assert response.status_code == 200
    assert response.json()["details"] == {
        "project": project["id"],
        "archived": True,
        "historyPreserved": True,
        "sourceRemoved": True,
    }
    assert client.get("/api/projects", params={"paged": "false"}).json() == []
    assert not project_root.exists()
    with db_module.db() as connection:
        archived = connection.execute(
            "select archived_at from projects where id=?", (project["id"],)
        ).fetchone()
        assert archived["archived_at"]
        assert connection.execute("select count(*) as count from tasks where id='task-history'").fetchone()["count"] == 1
        assert connection.execute("select count(*) as count from backtest_runs where id='run-history'").fetchone()["count"] == 1


def test_delete_project_with_active_reference_hides_project_without_removing_source(tmp_path, monkeypatch):
    db_module = configure_temp_db(tmp_path, monkeypatch)
    from app.main import app

    client = TestClient(app)
    project = client.post(
        "/api/projects",
        json={"name": "referenced-project", "language": "Python", "templateKey": "ema_cross"},
    ).json()
    project_root = Path(project["project_path"])
    with db_module.db() as connection:
        connection.execute(
            """
            insert into tasks
                (id,kind,status,title,project_id,parameters_json,log_path,created_at)
            values ('task-active','backtest','running','active',?,'{}',?,'2026-08-01')
            """,
            (project["id"], str(tmp_path / "active.log")),
        )

    response = client.delete(f"/api/projects/{project['id']}")

    assert response.status_code == 200
    assert response.json()["details"]["sourceRemoved"] is False
    assert client.get("/api/projects", params={"paged": "false"}).json() == []
    assert project_root.exists()


def test_consolidate_automatic_copies_preserves_run_and_task_history(tmp_path, monkeypatch):
    db_module = configure_temp_db(tmp_path, monkeypatch)
    import app.services.projects as projects

    base = projects.create_project("macd", template_key="macd", market="china")
    copied = projects.clone_project(base["id"], "macd (copy 20260716-225730)")
    copied_path = Path(copied["project_path"])
    with db_module.db() as connection:
        connection.execute(
            """
            insert into tasks
                (id, kind, status, title, project_id, parameters_json, log_path, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("task-copy", "backtest", "failed", "copied run", copied["id"], "{}", str(tmp_path / "task.log"), "2026-07-16T00:00:00+00:00"),
        )
        connection.execute(
            """
            insert into backtest_runs
                (id, task_id, project_id, symbol, asset_class, venue, resolution, data_type,
                 parameters_json, status, docker_image, results_dir, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "run-copy",
                "task-copy",
                copied["id"],
                "600460",
                "equity",
                "china",
                "daily",
                "trade",
                '{"ticker":"600460","start":"2024-01-01","end":"2024-01-02","cash":100000}',
                "failed",
                "lean:test",
                str(tmp_path / "runs" / "run-copy" / "results"),
                "2026-07-16T00:00:00+00:00",
            ),
        )

    result = projects.consolidate_automatic_copies()

    assert result["merged"] == [{"source": copied["id"], "target": base["id"]}]
    assert not copied_path.exists()
    with db_module.db() as connection:
        assert connection.execute("select project_id from tasks where id = 'task-copy'").fetchone()["project_id"] == base["id"]
        assert connection.execute("select project_id from backtest_runs where id = 'run-copy'").fetchone()["project_id"] == base["id"]
        assert connection.execute("select count(*) as count from projects").fetchone()["count"] == 1


def test_backtest_uses_immutable_project_snapshot(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)
    import app.services.backtest_service as backtest_service
    import app.services.projects as projects
    import app.services.tasks as task_service

    monkeypatch.setattr(backtest_service, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(task_service, "RUNS_DIR", tmp_path / "runs")
    project = projects.create_project("snapshot-project", template_key="ema_cross")
    original = (Path(project["project_path"]) / project["main_file"]).read_text(encoding="utf-8")

    job = backtest_service.create_backtest_job(
        {
            "symbol": "AAPL",
            "assetClass": "equity",
            "market": "usa",
            "start": "2024-01-02",
            "end": "2024-01-04",
            "cash": 100000,
            "projectId": project["id"],
        }
    )
    snapshot = Path(str(job["parameters"]["strategySnapshotDir"])) / project["main_file"]
    projects.write_file(project["id"], project["main_file"], "# changed after queue\n")

    assert snapshot.read_text(encoding="utf-8") == original
    assert (Path(project["project_path"]) / project["main_file"]).read_text(encoding="utf-8") == "# changed after queue\n"

    frozen_source = tmp_path / "runs" / "trusted-source" / "strategy"
    frozen_source.mkdir(parents=True)
    (frozen_source / "frozen.py").write_text("class FrozenAlgorithm: pass\n", encoding="utf-8")
    paper_job = backtest_service.create_backtest_job(
        {
            "symbol": "AAPL",
            "assetClass": "equity",
            "market": "usa",
            "start": "2024-01-02",
            "end": "2024-01-05",
            "cash": 100000,
            "projectId": project["id"],
            "strategySnapshotSourceDir": str(frozen_source),
            "strategySnapshotMainFile": "frozen.py",
            "strategySnapshotAlgorithmClass": "FrozenAlgorithm",
            "strategySnapshotLanguage": "Python",
        }
    )
    paper_snapshot = Path(str(paper_job["parameters"]["strategySnapshotDir"]))
    assert (paper_snapshot / "frozen.py").read_text(encoding="utf-8") == "class FrozenAlgorithm: pass\n"
    assert paper_job["parameters"]["strategySnapshotMainFile"] == "frozen.py"
    assert paper_job["parameters"]["strategySnapshotAlgorithmClass"] == "FrozenAlgorithm"
