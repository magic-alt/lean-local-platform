from __future__ import annotations

import csv
import io
import itertools
import shutil
import statistics as stats_module
import uuid
from datetime import date, timedelta
from typing import Any

from ..core.config import RUNS_DIR
from ..core.errors import LeanWebError, NotFoundError
from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now
from .ashare_repository import universe_as_of
from .optimization import normalize_parameter_grid
from .projects import get_project
from .settings import get_settings


TERMINAL = {"success", "failed", "skipped", "cancelled"}
ACTIVE = {"dispatching", "queued", "running"}


def _symbols(config: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    direct = sorted({str(value).strip().upper() for value in config.get("symbols") or [] if str(value).strip()})
    if direct:
        return direct, {"type": "symbols", "symbols": direct}
    symbol = str(config.get("symbol") or "").strip().upper()
    if symbol:
        return [symbol], {"type": "symbols", "symbols": [symbol]}
    universe_code = str(config.get("universeCode") or "").strip().upper()
    if not universe_code:
        raise LeanWebError("Select at least one symbol or a universeCode.")
    as_of = str(config.get("asOfDate") or config.get("start") or date.today().isoformat())[:10]
    members = universe_as_of(universe_code, as_of)
    symbols = sorted({str(item.get("symbol") or "").upper() for item in members if item.get("symbol")})
    if not symbols:
        raise LeanWebError(f"No point-in-time members are available for {universe_code} on {as_of}.")
    return symbols, {"type": "universe", "universeCode": universe_code, "asOfDate": as_of, "symbols": symbols}


def _projects(config: dict[str, Any]) -> list[str]:
    values = config.get("projectIds") or ([config.get("projectId")] if config.get("projectId") else [])
    result = []
    for value in values:
        project_id = str(value or "").strip()
        if project_id and project_id not in result:
            get_project(project_id)
            result.append(project_id)
    if not result:
        raise LeanWebError("At least one projectId is required.")
    return result


def _base_request(config: dict[str, Any], project_id: str, symbol: str) -> dict[str, Any]:
    project = get_project(project_id)
    project_config = project.get("config") or {}
    market = str(config.get("market") or project_config.get("market") or "china")
    return {
        "projectId": project_id,
        "symbol": symbol,
        "name": str(config.get("name") or "Batch Backtest"),
        "assetClass": str(config.get("assetClass") or project_config.get("assetClass") or "equity"),
        "market": market,
        "venue": str(config.get("venue") or project_config.get("venue") or market),
        "resolution": str(config.get("resolution") or project_config.get("resolution") or "daily"),
        "dataType": str(config.get("dataType") or project_config.get("dataType") or "trade"),
        "start": str(config.get("start") or "2020-01-01"),
        "end": str(config.get("end") or date.today().isoformat()),
        "cash": float(config.get("cash") or 300000),
        "dockerImage": config.get("dockerImage") or get_settings()["dockerImage"],
        "parameters": {**dict(project_config.get("parameters") or {}), **dict(config.get("parameters") or {})},
    }


def _rolling_windows(config: dict[str, Any]) -> list[tuple[str, str]]:
    windows = config.get("windows") or []
    normalized = [(str(item["start"]), str(item["end"])) for item in windows if item.get("start") and item.get("end")]
    if normalized:
        return normalized
    start = date.fromisoformat(str(config.get("start") or "2020-01-01")[:10])
    end = date.fromisoformat(str(config.get("end") or date.today().isoformat())[:10])
    windows = []
    cursor = start
    while cursor <= end:
        try:
            next_cursor = cursor.replace(year=cursor.year + 1)
        except ValueError:
            next_cursor = cursor.replace(month=2, day=28, year=cursor.year + 1)
        window_end = min(end, next_cursor - timedelta(days=1))
        windows.append((cursor.isoformat(), window_end.isoformat()))
        cursor = next_cursor
    return windows


def _walk_forward_windows(config: dict[str, Any]) -> list[dict[str, Any]]:
    start = date.fromisoformat(str(config.get("start") or "2018-01-01")[:10])
    end = date.fromisoformat(str(config.get("end") or date.today().isoformat())[:10])
    train_years = max(1, int(config.get("trainYears") or 3))
    test_years = max(1, int(config.get("testYears") or 1))
    step_years = max(1, int(config.get("stepYears") or 1))
    folds: list[dict[str, Any]] = []
    fold_start = start
    fold = 1
    while True:
        try:
            test_start = fold_start.replace(year=fold_start.year + train_years)
            test_end_exclusive = test_start.replace(year=test_start.year + test_years)
        except ValueError:
            test_start = fold_start.replace(month=2, day=28, year=fold_start.year + train_years)
            test_end_exclusive = test_start.replace(year=test_start.year + test_years)
        if test_start > end:
            break
        test_end = min(end, test_end_exclusive - timedelta(days=1))
        folds.extend(
            [
                {"fold": fold, "phase": "train", "start": fold_start.isoformat(), "end": (test_start - timedelta(days=1)).isoformat()},
                {"fold": fold, "phase": "test", "start": test_start.isoformat(), "end": test_end.isoformat()},
            ]
        )
        try:
            fold_start = fold_start.replace(year=fold_start.year + step_years)
        except ValueError:
            fold_start = fold_start.replace(month=2, day=28, year=fold_start.year + step_years)
        fold += 1
        if test_end >= end:
            break
    if not folds:
        raise LeanWebError("Walk-forward requires enough history for at least one train/test fold.")
    return folds


def _membership_schedule(universe_code: str, start: str, end: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            """
            select symbol,start_date,end_date,announce_date,effective_date,weight
            from universe_membership
            where universe_code=? and start_date<=? and (end_date is null or end_date>=?)
              and (announce_date is null or announce_date<=coalesce(effective_date,start_date))
            order by start_date,symbol
            """,
            (universe_code, end, start),
        ).fetchall()
    return [
        {
            "symbol": str(row["symbol"]).upper(),
            "startDate": max(str(row["effective_date"] or row["start_date"]), start),
            "endDate": min(str(row["end_date"]), end) if row["end_date"] else None,
            "weight": row["weight"],
        }
        for row in rows
        if str(row["effective_date"] or row["start_date"]) <= end
    ]


def expand(config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    kind = str(config.get("kind") or "backtest")
    mode = str(config.get("mode") or "independent")
    if kind == "research":
        factor_names = config.get("factorNames") or [config.get("factorName") or "momentum"]
        items = [
            {
                "key": f"research:{name}",
                "projectId": config.get("projectId"),
                "symbol": None,
                "parameters": {**config, "factorName": name},
            }
            for name in factor_names
        ]
        return items, {"type": "research", "factorNames": factor_names}

    projects = _projects(config)
    symbols, selection = _symbols(config)
    if mode == "dynamic_universe":
        universe_code = str(config.get("universeCode") or "CSI300").upper()
        request = _base_request(config, projects[0], symbols[0])
        schedule = _membership_schedule(universe_code, request["start"], request["end"])
        if not schedule:
            raise LeanWebError(f"No historical PIT schedule is available for {universe_code} in the selected range.")
        request["parameters"].update({"universeCode": universe_code, "dynamicUniverse": True, "universeSchedule": __import__("json").dumps(schedule, ensure_ascii=False, separators=(",", ":")), "universeSymbols": sorted({row["symbol"] for row in schedule})})
        return [{"key": f"{projects[0]}:dynamic:{universe_code}", "projectId": projects[0], "symbol": symbols[0], "parameters": request}], selection

    parameter_sets_by_project: dict[str, tuple[list[str], list[dict[str, Any]]]] = {}
    project_grids = config.get("parameterGrids") or {}
    for project_id in projects:
        parameter_sets: list[dict[str, Any]] = [dict(config.get("parameters") or {})]
        grid_keys: list[str] = []
        if kind == "optimization" or mode in {"single_symbol_grid", "universe_robust", "walk_forward", "multi_strategy"}:
            raw_grid = project_grids.get(project_id) or config.get("parameterGrid") or {}
            grid = normalize_parameter_grid(raw_grid, max_candidates=int(config.get("maxCandidates") or 200))
            grid_keys = list(grid)
            parameter_sets = [dict(zip(grid_keys, values, strict=True)) for values in itertools.product(*(grid[key] for key in grid_keys))]
        parameter_sets_by_project[project_id] = (grid_keys, parameter_sets)
    if mode == "walk_forward":
        window_specs = _walk_forward_windows(config)
    elif mode == "rolling":
        window_specs = [{"fold": index, "phase": "rolling", "start": start, "end": end} for index, (start, end) in enumerate(_rolling_windows(config), start=1)]
    else:
        window_specs = [{"fold": 1, "phase": "full", "start": str(config.get("start") or "2020-01-01"), "end": str(config.get("end") or date.today().isoformat())}]
    items = []
    for project_id in projects:
        grid_keys, parameter_sets = parameter_sets_by_project[project_id]
        for symbol, window, overrides in itertools.product(symbols, window_specs, parameter_sets):
            request = _base_request(config, project_id, symbol)
            request["start"], request["end"] = window["start"], window["end"]
            suffix = ",".join(f"{key}={overrides.get(key)}" for key in grid_keys) or "base"
            request["parameters"].update(
                {
                    **overrides,
                    "optimizationOverrides": overrides,
                    "optimizationCandidateKey": suffix,
                    "experimentMode": mode,
                    "experimentFold": window["fold"],
                    "experimentPhase": window["phase"],
                }
            )
            items.append(
                {
                    "key": f"{project_id}:{symbol}:{window['fold']}:{window['phase']}:{window['start']}:{window['end']}:{suffix}",
                    "projectId": project_id,
                    "symbol": symbol,
                    "parameters": request,
                }
            )
    return items, selection


def preview(config: dict[str, Any]) -> dict[str, Any]:
    items, selection = expand(config)
    limit = max(1, min(50000, int(get_settings().get("maxBatchRuns") or 5000)))
    count = len(items)
    return {
        "kind": str(config.get("kind") or "backtest"),
        "mode": str(config.get("mode") or "independent"),
        "expandedCount": count,
        "limit": limit,
        "withinLimit": count <= limit,
        "selection": selection,
        "effectiveConcurrency": int(get_settings().get("maxConcurrentJobs") or 1),
        "sample": [{key: item.get(key) for key in ("key", "projectId", "symbol")} for item in items[:20]],
        "warnings": [] if count <= limit else [f"Batch expands to {count} runs; the configured limit is {limit}."],
    }


def create_batch(config: dict[str, Any]) -> dict[str, Any]:
    report = preview(config)
    if not report["withinLimit"]:
        raise LeanWebError(report["warnings"][0])
    items, selection = expand(config)
    batch_id = str(uuid.uuid4())
    now = utc_now()
    snapshot_root = RUNS_DIR / "batches" / batch_id / "strategies"
    snapshots: dict[str, str] = {}
    for project_id in sorted({str(item.get("projectId")) for item in items if item.get("projectId")}):
        project = get_project(project_id)
        target = snapshot_root / project_id
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(project["project_path"], target)
        snapshots[project_id] = str(target)
    for item in items:
        if item.get("projectId") in snapshots:
            item["parameters"]["sharedStrategySnapshotDir"] = snapshots[item["projectId"]]
    stored_config = {**config, "resolvedSelection": selection, "strategySnapshots": snapshots}
    with db() as connection:
        connection.execute(
            """
            insert into experiment_batches
                (id,kind,mode,name,example_key,status,config_json,total,queued,created_at)
            values (?,?,?,?,?,'queued',?,?,?,?)
            """,
            (
                batch_id,
                str(config.get("kind") or "backtest"),
                str(config.get("mode") or "independent"),
                str(config.get("name") or "Experiment Batch"),
                config.get("exampleKey"),
                json_dump(stored_config),
                len(items),
                len(items),
                now,
            ),
        )
        connection.executemany(
            """
            insert into experiment_batch_items
                (id,batch_id,item_index,item_key,project_id,symbol,status,parameters_json,created_at)
            values (?,?,?,?,?,?,'pending',?,?)
            """,
            [
                (str(uuid.uuid4()), batch_id, index, item["key"], item.get("projectId"), item.get("symbol"), json_dump(item["parameters"]), now)
                for index, item in enumerate(items, start=1)
            ],
        )
    return detail(batch_id)


def list_batches() -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute("select * from experiment_batches order by created_at desc").fetchall()
    return rows_to_dicts(rows)


def _metric(statistics: dict[str, Any], *keys: str) -> Any:
    lowered = {str(key).casefold(): value for key, value in statistics.items()}
    for key in keys:
        if key.casefold() in lowered:
            return lowered[key.casefold()]
    return None


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace("%", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def _summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    ranked = []
    for item in items:
        result = item.get("result") or {}
        statistics = result.get("statistics") or {}
        request = item.get("parameters") or {}
        strategy_parameters = request.get("parameters") or {}
        ranked.append(
            {
                "itemId": item["id"],
                "runId": item.get("related_id"),
                "projectId": item.get("project_id"),
                "symbol": item.get("symbol"),
                "status": item.get("status"),
                "candidateKey": strategy_parameters.get("optimizationCandidateKey"),
                "overrides": strategy_parameters.get("optimizationOverrides") or {},
                "fold": strategy_parameters.get("experimentFold"),
                "phase": strategy_parameters.get("experimentPhase"),
                "sharpe": _number(_metric(statistics, "Sharpe Ratio", "Sharpe")),
                "return": _metric(statistics, "Net Profit", "Compounding Annual Return", "Total Return"),
                "drawdown": _metric(statistics, "Drawdown", "Maximum Drawdown"),
                "trades": _metric(statistics, "Total Orders", "Total Trades"),
                "error": item.get("error"),
            }
        )
    ranked.sort(key=lambda item: item["sharpe"] if item["sharpe"] is not None else float("-inf"), reverse=True)
    candidate_groups: dict[str, list[dict[str, Any]]] = {}
    for item in ranked:
        if item.get("candidateKey"):
            candidate_groups.setdefault(f"{item.get('projectId')}:{item['candidateKey']}", []).append(item)
    candidates = []
    for key, group in candidate_groups.items():
        successful = [item for item in group if item["status"] == "success" and item["sharpe"] is not None]
        values = [float(item["sharpe"]) for item in successful]
        coverage = len(successful) / len(group) if group else 0.0
        candidates.append(
            {
                "key": key,
                "projectId": group[0].get("projectId"),
                "candidateKey": group[0].get("candidateKey"),
                "overrides": group[0].get("overrides"),
                "runs": len(group),
                "successes": len(successful),
                "coverage": coverage,
                "valid": coverage >= 0.8,
                "medianSharpe": stats_module.median(values) if values else None,
                "p25Sharpe": sorted(values)[max(0, int(len(values) * 0.25) - 1)] if values else None,
            }
        )
    candidates.sort(key=lambda item: (bool(item["valid"]), item["medianSharpe"] if item["medianSharpe"] is not None else float("-inf")), reverse=True)
    walk_forward = []
    folds = sorted({int(item["fold"]) for item in ranked if item.get("phase") == "train" and item.get("fold") is not None})
    for fold in folds:
        train = [item for item in ranked if item.get("fold") == fold and item.get("phase") == "train" and item.get("status") == "success" and item.get("sharpe") is not None]
        best_train = max(train, key=lambda item: float(item["sharpe"]), default=None)
        test = next((item for item in ranked if best_train and item.get("fold") == fold and item.get("phase") == "test" and item.get("projectId") == best_train.get("projectId") and item.get("symbol") == best_train.get("symbol") and item.get("candidateKey") == best_train.get("candidateKey")), None)
        if best_train:
            walk_forward.append({"fold": fold, "selected": best_train.get("overrides"), "trainSharpe": best_train.get("sharpe"), "testSharpe": test.get("sharpe") if test else None, "trainRunId": best_train.get("runId"), "testRunId": test.get("runId") if test else None})
    return {"rankingMetric": "sharpe", "ranking": ranked, "candidates": candidates, "walkForward": walk_forward}


def refresh(batch_id: str) -> dict[str, Any]:
    with db() as connection:
        item_rows = connection.execute("select * from experiment_batch_items where batch_id=? order by item_index", (batch_id,)).fetchall()
        batch_row = connection.execute("select * from experiment_batches where id=?", (batch_id,)).fetchone()
    if not batch_row:
        raise NotFoundError("Experiment batch not found.")
    items = rows_to_dicts(item_rows)
    counts = {key: sum(1 for item in items if item["status"] == key) for key in ("pending", "dispatching", "queued", "running", "success", "failed", "skipped", "cancelled")}
    completed = counts["success"] + counts["failed"] + counts["skipped"] + counts["cancelled"]
    active = counts["dispatching"] + counts["queued"] + counts["running"]
    cancel_requested = bool(batch_row["cancel_requested"])
    if completed == len(items):
        status = "cancelled" if cancel_requested and not counts["success"] else "partial" if counts["failed"] or counts["skipped"] or counts["cancelled"] else "success"
        finished_at = batch_row["finished_at"] or utc_now()
    else:
        status = "running" if active or counts["success"] or counts["failed"] else "queued"
        finished_at = None
    summary = _summary(items)
    with db() as connection:
        connection.execute(
            """
            update experiment_batches set status=?,summary_json=?,queued=?,running=?,succeeded=?,failed=?,skipped=?,cancelled=?,
                started_at=case when ?='running' then coalesce(started_at,?) else started_at end,finished_at=? where id=?
            """,
            (status, json_dump(summary), counts["pending"] + counts["dispatching"] + counts["queued"], counts["running"], counts["success"], counts["failed"], counts["skipped"], counts["cancelled"], status, utc_now(), finished_at, batch_id),
        )
    return detail(batch_id, refresh_state=False)


def detail(batch_id: str, *, refresh_state: bool = True) -> dict[str, Any]:
    if refresh_state:
        return refresh(batch_id)
    with db() as connection:
        row = connection.execute("select * from experiment_batches where id=?", (batch_id,)).fetchone()
        items = connection.execute("select * from experiment_batch_items where batch_id=? order by item_index", (batch_id,)).fetchall()
    batch = row_to_dict(row)
    if batch is None:
        raise NotFoundError("Experiment batch not found.")
    batch["items"] = rows_to_dicts(items)
    return batch


def dispatch_window(batch_id: str) -> dict[str, Any]:
    batch = detail(batch_id)
    if batch.get("cancel_requested") or batch["status"] in TERMINAL:
        return batch
    settings = get_settings()
    window = max(4, 2 * int(settings.get("maxConcurrentJobs") or 1))
    active = sum(1 for item in batch["items"] if item["status"] in ACTIVE)
    available = max(0, window - active)
    for item in [entry for entry in batch["items"] if entry["status"] == "pending"][:available]:
        _dispatch_item(batch, item)
    return refresh(batch_id)


def _dispatch_item(batch: dict[str, Any], item: dict[str, Any]) -> None:
    from ..tasks.worker import dispatch_experiment_batch_task, run_backtest_task, run_research_batch_item_task
    from .backtest_service import create_backtest_job, create_failed_backtest_job, fail_backtest_queue, mark_backtest_queued

    with db() as connection:
        cursor = connection.execute("update experiment_batch_items set status='dispatching' where id=? and status='pending'", (item["id"],))
        if getattr(cursor, "rowcount", 0) != 1:
            return
    attempt = int(item.get("attempt") or 0) + 1
    if batch["kind"] == "research":
        try:
            task = run_research_batch_item_task.apply_async(args=[batch["id"], item["id"]], queue="default")
        except Exception as exc:
            with db() as connection:
                connection.execute("update experiment_batch_items set status='failed',attempt=?,error=?,finished_at=? where id=?", (attempt, str(exc), utc_now(), item["id"]))
                connection.execute("insert into experiment_batch_attempts (id,item_id,attempt,status,error,created_at,finished_at) values (?,?,?,'failed',?,?,?)", (str(uuid.uuid4()), item["id"], attempt, str(exc), utc_now(), utc_now()))
            dispatch_experiment_batch_task.apply_async(args=[batch["id"]], queue="default")
            return
        with db() as connection:
            connection.execute("update experiment_batch_items set status='queued',attempt=?,task_id=? where id=?", (attempt, task.id, item["id"]))
            connection.execute("insert into experiment_batch_attempts (id,item_id,attempt,task_id,status,created_at) values (?,?,?,?, 'queued',?)", (str(uuid.uuid4()), item["id"], attempt, task.id, utc_now()))
        return
    request = dict(item.get("parameters") or {})
    request["name"] = f"{batch['name']} · {item.get('symbol') or item['item_index']}"
    try:
        run = create_backtest_job(request)
    except Exception as exc:
        run = create_failed_backtest_job(request, str(exc))
        with db() as connection:
            connection.execute("update experiment_batch_items set status='failed',attempt=?,related_id=?,task_id=?,error=?,finished_at=? where id=?", (attempt, run.get("id"), run.get("task_id"), str(exc), utc_now(), item["id"]))
        dispatch_experiment_batch_task.apply_async(args=[batch["id"]], queue="default")
        return
    with db() as connection:
        connection.execute("update backtest_runs set batch_item_id=? where id=?", (item["id"], run["id"]))
        connection.execute("update experiment_batch_items set status='queued',attempt=?,related_id=?,task_id=? where id=?", (attempt, run["id"], run.get("task_id"), item["id"]))
        connection.execute("insert into experiment_batch_attempts (id,item_id,attempt,related_id,task_id,status,created_at) values (?,?,?,?,?,'queued',?)", (str(uuid.uuid4()), item["id"], attempt, run["id"], run.get("task_id"), utc_now()))
    try:
        result = run_backtest_task.apply_async(args=[run["task_id"], run["id"]], queue="backtest")
    except Exception as exc:
        fail_backtest_queue(run["id"], str(exc))
        reconcile_backtest(run["id"])
        return
    from .tasks import update_task

    update_task(run["task_id"], celery_task_id=result.id, status="queued")
    mark_backtest_queued(run["id"])


def reconcile_backtest(run_id: str) -> None:
    with db() as connection:
        run_row = connection.execute("select id,batch_item_id,status,statistics_json,error,error_message,started_at,finished_at from backtest_runs where id=?", (run_id,)).fetchone()
    run = dict(run_row) if run_row else None
    if not run or not run.get("batch_item_id"):
        return
    status = str(run["status"])
    item_status = status if status in TERMINAL | {"queued", "running"} else "failed"
    result = {"statistics": __import__("json").loads(run["statistics_json"] or "{}")}
    with db() as connection:
        connection.execute(
            "update experiment_batch_items set status=?,result_json=?,error=?,started_at=coalesce(started_at,?),finished_at=? where id=?",
            (item_status, json_dump(result), run.get("error_message") or run.get("error"), run.get("started_at"), run.get("finished_at"), run["batch_item_id"]),
        )
        item = connection.execute("select batch_id,attempt from experiment_batch_items where id=?", (run["batch_item_id"],)).fetchone()
        connection.execute("update experiment_batch_attempts set status=?,error=?,finished_at=? where item_id=? and attempt=?", (item_status, run.get("error_message") or run.get("error"), run.get("finished_at"), run["batch_item_id"], item["attempt"]))
    if item_status in TERMINAL:
        from ..tasks.worker import dispatch_experiment_batch_task

        dispatch_experiment_batch_task.apply_async(args=[item["batch_id"]], queue="default")


def finish_research_item(batch_id: str, item_id: str, *, result: dict[str, Any] | None = None, error: str | None = None) -> None:
    status = "failed" if error else "success"
    with db() as connection:
        connection.execute("update experiment_batch_items set status=?,result_json=?,error=?,finished_at=? where id=?", (status, json_dump(result or {}), error, utc_now(), item_id))
        item = connection.execute("select attempt from experiment_batch_items where id=?", (item_id,)).fetchone()
        if item:
            connection.execute("update experiment_batch_attempts set status=?,error=?,finished_at=? where item_id=? and attempt=?", (status, error, utc_now(), item_id, item["attempt"]))
    refresh(batch_id)


def cancel(batch_id: str) -> dict[str, Any]:
    from .backtest_service import cancel_backtest

    batch = detail(batch_id)
    with db() as connection:
        connection.execute("update experiment_batches set cancel_requested=1 where id=?", (batch_id,))
        connection.execute("update experiment_batch_items set status='cancelled',finished_at=? where batch_id=? and status in ('pending','dispatching','queued')", (utc_now(), batch_id))
    for item in batch["items"]:
        if item["status"] in ACTIVE and item.get("related_id"):
            cancel_backtest(str(item["related_id"]))
    return refresh(batch_id)


def retry_failed(batch_id: str) -> dict[str, Any]:
    batch = detail(batch_id)
    if batch["status"] not in TERMINAL | {"partial"}:
        raise LeanWebError("Only a completed batch can retry failed items.")
    with db() as connection:
        connection.execute("update experiment_batches set status='queued',cancel_requested=0,finished_at=null where id=?", (batch_id,))
        connection.execute("update experiment_batch_items set status='pending',related_id=null,task_id=null,error=null,started_at=null,finished_at=null where batch_id=? and status in ('failed','skipped')", (batch_id,))
    return dispatch_window(batch_id)


def export_csv(batch_id: str) -> str:
    batch = detail(batch_id)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["item", "projectId", "symbol", "status", "runId", "sharpe", "return", "drawdown", "trades", "error"])
    writer.writeheader()
    ranking = {item["itemId"]: item for item in (batch.get("summary") or {}).get("ranking", [])}
    for item in batch["items"]:
        metrics = ranking.get(item["id"], {})
        writer.writerow({"item": item["item_key"], "projectId": item.get("project_id"), "symbol": item.get("symbol"), "status": item["status"], "runId": item.get("related_id"), "sharpe": metrics.get("sharpe"), "return": metrics.get("return"), "drawdown": metrics.get("drawdown"), "trades": metrics.get("trades"), "error": item.get("error")})
    return output.getvalue()
