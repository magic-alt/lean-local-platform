from pathlib import Path


def configure(tmp_path, monkeypatch):
    import app.db as db_module
    import app.core.config as config_module
    import app.services.projects as projects_module
    import app.services.experiment_batches as batches_module

    db_path = tmp_path / "test.sqlite3"
    monkeypatch.setattr(db_module, "DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.setattr(db_module, "SQLITE_TEST_BACKEND_ENABLED", True)
    monkeypatch.setattr(db_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(config_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(db_module, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(projects_module, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(batches_module, "RUNS_DIR", tmp_path / "runs")
    db_module.init_db()
    return db_module


def seed_universe(db_module):
    with db_module.db() as connection:
        connection.executemany(
            """
            insert into securities
                (symbol,name,exchange,market,listed_date,status,is_st,created_at,updated_at)
            values (?,?,?,'china','2000-01-01','listed',0,'2026-01-01','2026-01-01')
            """,
            [("000001", "One", "SZSE"), ("600519", "Two", "SSE")],
        )
        connection.executemany(
            """
            insert into universe_membership
                (universe_code,symbol,start_date,end_date,announce_date,effective_date,weight,source,batch_id)
            values ('CSI300',?,? ,?, ?, ?,1,'unit','batch')
            """,
            [
                ("000001", "2020-01-01", None, "2019-12-01", "2020-01-01"),
                ("600519", "2021-01-01", None, "2020-12-01", "2021-01-01"),
            ],
        )


def test_example_catalog_instantiates_editable_research_project(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    from app.services import examples

    catalog = examples.list_examples("research", "PIT")
    assert [item["key"] for item in catalog] == ["pit-turnover"]

    result = examples.instantiate_example("research", "pit-turnover", name="PIT study")
    project = result["project"]
    notebook = Path(project["project_path"]) / "notebooks" / "pit-turnover.ipynb"
    assert notebook.is_file()
    assert project["config"]["exampleKey"] == "pit-turnover"
    assert project["config"]["exampleVersion"] == 1


def test_batch_preview_freezes_pit_members_and_expands_project_matrix(tmp_path, monkeypatch):
    db_module = configure(tmp_path, monkeypatch)
    seed_universe(db_module)
    from app.services import experiment_batches
    from app.services.projects import create_project

    first = create_project("first", template_key="ema_cross", market="china")
    second = create_project("second", template_key="rsi_reversion", market="china")
    config = {
        "kind": "backtest",
        "mode": "independent",
        "projectIds": [first["id"], second["id"]],
        "universeCode": "CSI300",
        "start": "2022-01-01",
        "end": "2023-01-01",
    }
    report = experiment_batches.preview(config)
    assert report["expandedCount"] == 4
    assert report["selection"]["symbols"] == ["000001", "600519"]

    batch = experiment_batches.create_batch(config)
    assert batch["total"] == 4
    assert batch["config"]["resolvedSelection"]["asOfDate"] == "2022-01-01"
    assert len(batch["items"]) == 4


def test_dynamic_universe_persists_effective_membership_schedule(tmp_path, monkeypatch):
    db_module = configure(tmp_path, monkeypatch)
    seed_universe(db_module)
    from app.services import experiment_batches
    from app.services.projects import create_project

    project = create_project("dynamic", template_key="dynamic_universe", market="china")
    items, selection = experiment_batches.expand(
        {
            "kind": "backtest",
            "mode": "dynamic_universe",
            "projectId": project["id"],
            "universeCode": "CSI300",
            "start": "2020-06-01",
            "end": "2022-01-01",
        }
    )
    parameters = items[0]["parameters"]["parameters"]
    assert parameters["dynamicUniverse"] is True
    assert '"startDate":"2021-01-01"' in parameters["universeSchedule"]
    assert selection["asOfDate"] == "2020-06-01"


def test_help_docs_search_and_path_validation():
    from app.core.errors import NotFoundError
    from app.services import help_docs

    assert any(item["slug"] == "configuration" for item in help_docs.list_articles("maxBatchRuns"))
    assert help_docs.article("backtests")["title"] == "单次与批量回测"
    try:
        help_docs.article("../configuration")
    except NotFoundError:
        pass
    else:
        raise AssertionError("Path traversal must not resolve a help article")
