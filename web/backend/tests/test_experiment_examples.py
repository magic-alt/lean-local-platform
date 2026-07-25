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


def test_all_backtest_examples_reference_renderable_strategy_templates():
    from app.services import examples
    from app.services.strategies import get_template, render_python_template

    catalog = examples.list_examples("backtest")

    assert len(catalog) == 10
    for example in catalog:
        template = get_template(example["templateKey"])
        assert template["key"] == example["templateKey"]
        code = render_python_template(f"Example{example['key'].replace('-', '').title()}", template["key"])
        compile(code, f"<example:{example['key']}>", "exec")
        assert "constant benchmark fallback is disabled" in code


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


def test_batch_children_preserve_unified_market_and_execution_configuration(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    from app.services import experiment_batches
    from app.services.projects import create_project

    project = create_project("unified-config", template_key="buy_hold", market="china")
    items, _selection = experiment_batches.expand(
        {
            "kind": "backtest",
            "mode": "independent",
            "projectId": project["id"],
            "symbol": "000001",
            "market": "china",
            "start": "2024-01-01",
            "end": "2024-12-31",
            "benchmarkSymbol": "000300",
            "source": "tushare",
            "feeModel": "zero",
            "slippageModel": "zero",
            "allowResearchSource": True,
            "parameters": {
                "benchmarkSymbol": "000300",
                "commissionRate": 0,
                "slippageBps": 0,
            },
        }
    )

    request = items[0]["parameters"]
    assert request["market"] == "china"
    assert request["venue"] == "china"
    assert request["benchmarkSymbol"] == "000300"
    assert request["source"] == "tushare"
    assert request["feeModel"] == "zero"
    assert request["slippageModel"] == "zero"
    assert request["allowResearchSource"] is True
    assert request["parameters"]["commissionRate"] == 0
    assert request["parameters"]["slippageBps"] == 0


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


def test_walk_forward_expands_independent_validation_and_oos_with_lineage(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    from app.services import experiment_batches
    from app.services.projects import create_project
    from scripts import run_level4_audit

    project = create_project("walk-forward", template_key="ema_cross", market="china")
    config = {
        "kind": "backtest",
        "mode": "walk_forward",
        "projectId": project["id"],
        "symbol": "600519",
        "start": "2023-01-01",
        "end": "2025-12-31",
        "trainYears": 1,
        "testYears": 1,
        "stepYears": 1,
        "parameterGrid": {"fast": [10]},
        "minWalkForwardFolds": 2,
        "datasetVersion": "dataset:test:v1",
        "universeVersion": "symbols:600519:v1",
        "adjustmentContract": "raw-v1",
        "featurePipelineVersion": "features:test:v1",
    }

    items, _selection = experiment_batches.expand(config)

    assert len(items) == 6
    assert [
        (
            item["parameters"]["parameters"]["experimentFold"],
            item["parameters"]["parameters"]["experimentPhase"],
            item["parameters"]["start"],
            item["parameters"]["end"],
        )
        for item in items
    ] == [
        (1, "train", "2023-01-01", "2023-12-31"),
        (1, "validation", "2024-01-01", "2024-06-30"),
        (1, "oos", "2024-07-01", "2024-12-31"),
        (2, "train", "2024-01-01", "2024-12-31"),
        (2, "validation", "2025-01-01", "2025-06-30"),
        (2, "oos", "2025-07-01", "2025-12-31"),
    ]
    fold_fingerprints = {
        (
            item["parameters"]["parameters"]["experimentFold"],
            item["parameters"]["parameters"]["experimentFoldFingerprint"],
        )
        for item in items
    }
    assert len(fold_fingerprints) == 2
    assert all(
        len(item["parameters"]["parameters"]["experimentPhaseFingerprint"]) == 64
        for item in items
    )
    assert {
        item["parameters"]["parameters"]["experimentSelectionRole"] for item in items
    } == {"candidate_generation", "parameter_selection", "unbiased_evaluation"}

    audit_items = [
        {
            "id": item["key"],
            "status": "success",
            "projectId": item["projectId"],
            "symbol": item["symbol"],
            "parameters": item["parameters"],
        }
        for item in items
    ]
    status, warnings, failures = run_level4_audit._validate_case_result(
        "walk_forward",
        config,
        {"status": "success", "items": audit_items},
    )
    assert status == "failed"
    assert failures == ["walk_forward_evidence_missing"]
    assert not any("phase" in warning for warning in warnings)


def test_walk_forward_oos_is_blocked_until_validation_selection_is_frozen(tmp_path, monkeypatch):
    db_module = configure(tmp_path, monkeypatch)
    from app.services import experiment_batches
    from app.services.projects import create_project

    project = create_project("selection-gate", template_key="ema_cross", market="china")
    batch = experiment_batches.create_batch(
        {
            "kind": "optimization",
            "mode": "walk_forward",
            "projectId": project["id"],
            "symbol": "600519",
            "start": "2023-01-01",
            "end": "2024-12-31",
            "trainYears": 1,
            "testYears": 1,
            "validationMonths": 6,
            "parameterGrid": {"fast": [10, 20]},
            "datasetVersion": "dataset:test:v1",
            "universeVersion": "symbols:600519:v1",
            "adjustmentContract": "raw-v1",
            "featurePipelineVersion": "features:test:v1",
        }
    )
    oos = [
        item
        for item in batch["items"]
        if item["parameters"]["parameters"]["experimentPhase"] == "oos"
    ]
    assert {item["status"] for item in oos} == {"blocked_selection"}
    validation = [
        item
        for item in batch["items"]
        if item["parameters"]["parameters"]["experimentPhase"] == "validation"
    ]
    with db_module.db() as connection:
        for index, item in enumerate(validation, start=1):
            connection.execute(
                """
                update experiment_batch_items
                set status='success',result_json=?,finished_at='now'
                where id=?
                """,
                (
                    db_module.json_dump(
                        {
                            "statistics": {
                                "Sharpe Ratio": str(index),
                                "Net Profit": f"{index}%",
                                "Drawdown": f"{3-index}%",
                                "Total Orders": str(index + 2),
                            }
                        }
                    ),
                    item["id"],
                ),
            )

    refreshed = experiment_batches.refresh(batch["id"])
    refreshed_oos = [
        item
        for item in refreshed["items"]
        if item["parameters"]["parameters"]["experimentPhase"] == "oos"
    ]
    assert sorted(item["status"] for item in refreshed_oos) == ["pending", "skipped"]
    evidence = refreshed["walkForwardEvidence"]["windows"][0]
    assert evidence["selection"]["selection_metric"] == "validationSharpe"
    assert sum(int(item["selected"]) for item in evidence["candidates"]) == 1
    assert evidence["leakage"]["decision"] == "ALLOW"


def test_walk_forward_fails_closed_without_frozen_lineage(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    from app.core.errors import LeanWebError
    from app.services import experiment_batches
    from app.services.projects import create_project

    project = create_project("missing-lineage", template_key="ema_cross", market="china")
    try:
        experiment_batches.preview(
            {
                "kind": "optimization",
                "mode": "walk_forward",
                "projectId": project["id"],
                "symbol": "600519",
                "start": "2023-01-01",
                "end": "2024-12-31",
                "parameterGrid": {"fast": [10]},
            }
        )
    except LeanWebError as exc:
        assert "datasetVersion" in str(exc)
    else:
        raise AssertionError("walk-forward without frozen lineage must fail closed")


def test_batch_retry_and_restart_preserve_successful_children(tmp_path, monkeypatch):
    db_module = configure(tmp_path, monkeypatch)
    from app.services import experiment_batches
    from app.services.projects import create_project

    project = create_project("recovery", template_key="ema_cross", market="china")
    batch = experiment_batches.create_batch(
        {
            "kind": "backtest",
            "mode": "independent",
            "projectId": project["id"],
            "symbols": ["000001", "600519"],
            "start": "2024-01-01",
            "end": "2024-12-31",
        }
    )
    first, second = batch["items"]
    with db_module.db() as connection:
        connection.execute(
            """
            update experiment_batch_items
            set status='success',related_id='successful-run',finished_at='now'
            where id=?
            """,
            (first["id"],),
        )
        connection.execute(
            """
            update experiment_batch_items
            set status='failed',related_id='failed-run',error='boom',finished_at='now'
            where id=?
            """,
            (second["id"],),
        )

    dispatched = []
    monkeypatch.setattr(
        experiment_batches,
        "_dispatch_item",
        lambda _batch, item: dispatched.append(item["id"]),
    )
    retried = experiment_batches.retry_failed(batch["id"])

    by_id = {item["id"]: item for item in retried["items"]}
    assert by_id[first["id"]]["status"] == "success"
    assert by_id[first["id"]]["related_id"] == "successful-run"
    assert by_id[second["id"]]["status"] == "pending"
    assert by_id[second["id"]]["related_id"] is None
    assert dispatched == [second["id"]]

    cancelled = experiment_batches.cancel(batch["id"])
    assert cancelled["cancel_requested"] == 1
    assert {item["status"] for item in cancelled["items"]} == {"success", "cancelled"}

    dispatched.clear()
    restarted = experiment_batches.restart_cancelled(batch["id"])
    by_id = {item["id"]: item for item in restarted["items"]}
    assert by_id[first["id"]]["status"] == "success"
    assert by_id[first["id"]]["related_id"] == "successful-run"
    assert by_id[second["id"]]["status"] == "pending"
    assert dispatched == [second["id"]]


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
