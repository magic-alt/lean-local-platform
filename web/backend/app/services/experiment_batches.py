from __future__ import annotations

import csv
import hashlib
import io
import itertools
import json
import shutil
import statistics as stats_module
import uuid
from datetime import date, timedelta
from typing import Any

from ..core.config import RUNS_DIR
from ..core.errors import LeanWebError, NotFoundError
from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now
from .ashare_repository import universe_as_of
from .experiment_leakage import evaluate_experiment_leakage
from .optimization import normalize_parameter_grid
from .projects import get_project
from .settings import get_settings


TERMINAL = {"success", "failed", "skipped", "cancelled"}
ACTIVE = {"dispatching", "queued", "running"}
SELECTION_BLOCKED = "blocked_selection"

FUNDAMENTAL_FIELD_ALIASES = {
    "roe": "roe",
    "roe_waa": "roe",
    "roe_dt": "roe",
    "or_yoy": "revenueGrowth",
    "revenue_yoy": "revenueGrowth",
    "q_sales_yoy": "revenueGrowth",
    "tr_yoy": "revenueGrowth",
    "netprofit_yoy": "profitGrowth",
    "net_profit_yoy": "profitGrowth",
    "q_profit_yoy": "profitGrowth",
    "debt_to_assets": "debtRatio",
    "debt_assets_ratio": "debtRatio",
    "pe": "pe",
    "pe_ttm": "pe",
    "pb": "pb",
    "n_income": "netProfit",
    "net_profit": "netProfit",
}
INDEX_BENCHMARKS = {
    "CSI300": "000300",
    "CSI500": "000905",
    "CSI1000": "000852",
    "STAR50": "000688",
}


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


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
    request = {
        "projectId": project_id,
        "symbol": symbol,
        "name": str(config.get("name") or "Batch Backtest"),
        "assetClass": str(config.get("assetClass") or project_config.get("assetClass") or "equity"),
        "market": market,
        "venue": str(
            config.get("venue")
            or (market if config.get("market") else project_config.get("venue"))
            or market
        ),
        "resolution": str(config.get("resolution") or project_config.get("resolution") or "daily"),
        "dataType": str(config.get("dataType") or project_config.get("dataType") or "trade"),
        "start": str(config.get("start") or "2020-01-01"),
        "end": str(config.get("end") or date.today().isoformat()),
        "cash": float(config.get("cash") or 300000),
        "dockerImage": config.get("dockerImage") or get_settings()["dockerImage"],
        "parameters": {**dict(project_config.get("parameters") or {}), **dict(config.get("parameters") or {})},
    }
    for key in (
        "benchmarkSymbol",
        "source",
        "providerSource",
        "allowResearchSource",
        "feeModel",
        "slippageModel",
    ):
        if key in config:
            request[key] = config[key]
    return request


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
    evaluation_months = test_years * 12
    validation_months = int(config.get("validationMonths") or max(1, evaluation_months // 2))
    if validation_months <= 0 or validation_months >= evaluation_months:
        raise LeanWebError("Walk-forward validationMonths must leave a non-empty OOS window.")

    def add_years(value: date, years: int) -> date:
        try:
            return value.replace(year=value.year + years)
        except ValueError:
            return value.replace(month=2, day=28, year=value.year + years)

    def add_months(value: date, months: int) -> date:
        month_index = value.month - 1 + months
        year = value.year + month_index // 12
        month = month_index % 12 + 1
        day = value.day
        while day > 28:
            try:
                return value.replace(year=year, month=month, day=day)
            except ValueError:
                day -= 1
        return value.replace(year=year, month=month, day=day)

    folds: list[dict[str, Any]] = []
    fold_start = start
    fold = 1
    while True:
        validation_start = add_years(fold_start, train_years)
        validation_end_exclusive = add_months(validation_start, validation_months)
        oos_start = validation_end_exclusive
        oos_end_exclusive = add_years(validation_start, test_years)
        if oos_start > end:
            break
        oos_end = min(end, oos_end_exclusive - timedelta(days=1))
        windows = [
            {
                "fold": fold,
                "phase": "train",
                "role": "candidate_generation",
                "start": fold_start.isoformat(),
                "end": (validation_start - timedelta(days=1)).isoformat(),
            },
            {
                "fold": fold,
                "phase": "validation",
                "role": "parameter_selection",
                "start": validation_start.isoformat(),
                "end": (validation_end_exclusive - timedelta(days=1)).isoformat(),
            },
            {
                "fold": fold,
                "phase": "oos",
                "role": "unbiased_evaluation",
                "start": oos_start.isoformat(),
                "end": oos_end.isoformat(),
            },
        ]
        lineage = {
            "schemaVersion": 1,
            "fold": fold,
            "windows": [
                {"phase": item["phase"], "role": item["role"], "start": item["start"], "end": item["end"]}
                for item in windows
            ],
        }
        fold_fingerprint = hashlib.sha256(
            json.dumps(lineage, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        for item in windows:
            item["foldFingerprint"] = fold_fingerprint
            item["phaseFingerprint"] = hashlib.sha256(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "foldFingerprint": fold_fingerprint,
                        "phase": item["phase"],
                        "role": item["role"],
                        "start": item["start"],
                        "end": item["end"],
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
        folds.extend(windows)
        fold_start = add_years(fold_start, step_years)
        fold += 1
        if oos_end >= end:
            break
    if not folds:
        raise LeanWebError("Walk-forward requires enough history for at least one train/validation/OOS fold.")
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


def _chunks(values: list[str], size: int = 400) -> list[list[str]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def _fundamental_schedule(symbols: list[str], start: str, end: str) -> list[dict[str, Any]]:
    """Build a compact PIT metric stream without exposing post-publication data early."""
    tickers = sorted({str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()})
    if not tickers:
        return []
    raw_fields = sorted(FUNDAMENTAL_FIELD_ALIASES)
    field_rank = {field: index for index, field in enumerate(raw_fields)}
    chosen: dict[tuple[str, str, str], tuple[int, float]] = {}
    initial: dict[tuple[str, str], tuple[str, int, float]] = {}

    for chunk in _chunks(tickers):
        symbol_placeholders = ",".join("?" for _ in chunk)
        field_placeholders = ",".join("?" for _ in raw_fields)
        with db() as connection:
            rows = connection.execute(
                f"""
                select symbol,field_name,effective_date,announce_date,report_date,value
                from financial_facts
                where symbol in ({symbol_placeholders})
                  and field_name in ({field_placeholders})
                  and announce_date<=effective_date
                  and effective_date<=?
                order by effective_date,announce_date,report_date,field_name
                """,
                [*chunk, *raw_fields, end],
            ).fetchall()
        for row in rows_to_dicts(rows):
            symbol = str(row["symbol"]).upper()
            raw_field = str(row["field_name"])
            canonical = FUNDAMENTAL_FIELD_ALIASES[raw_field]
            effective_date = str(row["effective_date"])[:10]
            value = row.get("value")
            if value is None:
                continue
            candidate = (effective_date, field_rank[raw_field], float(value))
            if effective_date <= start:
                key = (symbol, canonical)
                current = initial.get(key)
                if (
                    current is None
                    or effective_date > current[0]
                    or (effective_date == current[0] and field_rank[raw_field] < current[1])
                ):
                    initial[key] = candidate
            else:
                key = (symbol, effective_date, canonical)
                current = chosen.get(key)
                if current is None or field_rank[raw_field] < current[0]:
                    chosen[key] = (field_rank[raw_field], float(value))

    for (symbol, canonical), (effective_date, rank, value) in initial.items():
        chosen[(symbol, effective_date, canonical)] = (rank, value)

    # Valuation factors are daily data. Retain the last observation in each
    # calendar month plus the start-date snapshot to keep LEAN parameters bounded.
    valuation_initial: dict[tuple[str, str], tuple[str, float]] = {}
    valuation_monthly: dict[tuple[str, str, str], tuple[str, float]] = {}
    for chunk in _chunks(tickers):
        placeholders = ",".join("?" for _ in chunk)
        with db() as connection:
            rows = connection.execute(
                f"""
                select symbol,factor_name,trade_date,value
                from factor_values
                where symbol in ({placeholders})
                  and factor_name in ('pe','pe_ttm','pb')
                  and trade_date<=?
                order by trade_date,factor_name
                """,
                [*chunk, end],
            ).fetchall()
        for row in rows_to_dicts(rows):
            symbol = str(row["symbol"]).upper()
            raw_field = str(row["factor_name"])
            canonical = FUNDAMENTAL_FIELD_ALIASES[raw_field]
            effective_date = str(row["trade_date"])[:10]
            value = row.get("value")
            if value is None:
                continue
            if effective_date <= start:
                valuation_initial[(symbol, canonical)] = (effective_date, float(value))
            else:
                valuation_monthly[(symbol, canonical, effective_date[:7])] = (effective_date, float(value))
    for (symbol, canonical), (effective_date, value) in valuation_initial.items():
        chosen[(symbol, effective_date, canonical)] = (-1, value)
    for (symbol, canonical, _month), (effective_date, value) in valuation_monthly.items():
        chosen[(symbol, effective_date, canonical)] = (-1, value)

    grouped: dict[tuple[str, str], dict[str, float]] = {}
    for (symbol, effective_date, canonical), (_rank, value) in chosen.items():
        grouped.setdefault((symbol, effective_date), {})[canonical] = value
    return [
        {"symbol": symbol, "effectiveDate": effective_date, "metrics": metrics}
        for (symbol, effective_date), metrics in sorted(grouped.items())
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
        universe_symbols = sorted({row["symbol"] for row in schedule})
        request["parameters"].update({"universeCode": universe_code, "dynamicUniverse": True, "universeSchedule": __import__("json").dumps(schedule, ensure_ascii=False, separators=(",", ":")), "universeSymbols": universe_symbols})
        project = get_project(projects[0])
        if str((project.get("config") or {}).get("templateKey") or "") == "ashare_index_screening":
            if universe_code not in INDEX_BENCHMARKS:
                raise LeanWebError("A-share index screening supports CSI300, CSI500, CSI1000 and STAR50.")
            fundamental_schedule = _fundamental_schedule(
                universe_symbols,
                request["start"],
                request["end"],
            )
            if not fundamental_schedule:
                raise LeanWebError(
                    f"No point-in-time fundamentals are available for {universe_code} in the selected range. "
                    "Sync daily_basic, income, balancesheet and fina_indicator before running this case."
                )
            benchmark = INDEX_BENCHMARKS[universe_code]
            request["benchmarkSymbol"] = benchmark
            request["parameters"].update(
                {
                    "benchmarkSymbol": benchmark,
                    "fundamentalSchedule": json.dumps(
                        fundamental_schedule,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    "fundamentalRecordCount": len(fundamental_schedule),
                }
            )
            selection = {
                **selection,
                "fundamentalRecordCount": len(fundamental_schedule),
                "benchmarkSymbol": benchmark,
            }
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
        required_lineage = (
            "datasetVersion",
            "universeVersion",
            "adjustmentContract",
            "featurePipelineVersion",
        )
        missing_lineage = [key for key in required_lineage if not str(config.get(key) or "").strip()]
        if missing_lineage:
            raise LeanWebError(
                "Walk-forward requires frozen lineage fields: " + ", ".join(missing_lineage) + "."
            )
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
                    "experimentSelectionRole": window.get("role"),
                    "experimentFoldFingerprint": window.get("foldFingerprint"),
                    "experimentPhaseFingerprint": window.get("phaseFingerprint"),
                    "datasetVersion": config.get("datasetVersion"),
                    "universeVersion": config.get("universeVersion"),
                    "adjustmentContract": config.get("adjustmentContract"),
                    "featurePipelineVersion": config.get("featurePipelineVersion"),
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


def _walk_forward_groups(items: list[dict[str, Any]]) -> dict[tuple[str, str, int], dict[str, Any]]:
    groups: dict[tuple[str, str, int], dict[str, Any]] = {}
    for item in items:
        request = item.get("parameters") or {}
        parameters = request.get("parameters") or {}
        fold = parameters.get("experimentFold")
        phase = str(parameters.get("experimentPhase") or "")
        if fold is None or phase not in {"train", "validation", "oos"}:
            continue
        key = (str(item.get("projectId") or ""), str(item.get("symbol") or ""), int(fold))
        group = groups.setdefault(
            key,
            {
                "projectId": key[0],
                "symbol": key[1],
                "fold": key[2],
                "phases": {},
                "candidates": {},
            },
        )
        candidate_key = str(parameters.get("optimizationCandidateKey") or "base")
        group["phases"].setdefault(phase, request)
        group["candidates"].setdefault(candidate_key, {})[phase] = item
    return groups


def _persist_walk_forward_plan(
    connection: Any,
    *,
    batch_id: str,
    config: dict[str, Any],
    items: list[dict[str, Any]],
    item_ids: dict[str, str],
    now: str,
) -> None:
    if str(config.get("mode") or "") != "walk_forward":
        return
    run_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"lean:walk-forward:{batch_id}"))
    connection.execute(
        """
        insert into walk_forward_runs
            (id,batch_id,status,dataset_version,universe_version,adjustment_contract,
             feature_pipeline_version,selection_metric,selection_rule,created_at)
        values (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            run_id,
            batch_id,
            "VALIDATION_PENDING",
            str(config["datasetVersion"]),
            str(config["universeVersion"]),
            str(config["adjustmentContract"]),
            str(config["featurePipelineVersion"]),
            str(config.get("selectionMetric") or "validationSharpe"),
            str(config.get("selectionRule") or "max(validationSharpe); tie=minDrawdown,minTurnover,candidateKey"),
            now,
        ),
    )
    lineage = dict(config.get("lineage") or {})
    for group_key, group in _walk_forward_groups(items).items():
        phases = group["phases"]
        train, validation, oos = phases["train"], phases["validation"], phases["oos"]
        parameters = train.get("parameters") or {}
        fold_fingerprint = str(parameters.get("experimentFoldFingerprint") or "")
        base_oos_input = {
            "foldFingerprint": fold_fingerprint,
            "datasetVersion": config["datasetVersion"],
            "universeVersion": config["universeVersion"],
            "adjustmentContract": config["adjustmentContract"],
            "featurePipelineVersion": config["featurePipelineVersion"],
            "oosStart": oos["start"],
            "oosEnd": oos["end"],
        }
        window_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"lean:walk-forward-window:{batch_id}:{group_key[0]}:{group_key[1]}:{group_key[2]}",
            )
        )
        leakage = evaluate_experiment_leakage(
            {
                "train": {"start": train["start"], "end": train["end"]},
                "validation": {"start": validation["start"], "end": validation["end"]},
                "oos": {"start": oos["start"], "end": oos["end"]},
                "labelHorizonDays": config.get("labelHorizonDays", 0),
            },
            {**lineage, **dict((lineage.get("folds") or {}).get(str(group["fold"])) or {})},
        )
        if leakage["decision"] != "ALLOW":
            codes = ",".join(item["code"] for item in leakage["violations"])
            raise LeanWebError(f"Walk-forward leakage check denied fold {group['fold']}: {codes}")
        connection.execute(
            """
            insert into walk_forward_windows
                (id,walk_forward_run_id,batch_id,project_id,symbol,fold,train_start,train_end,
                 validation_start,validation_end,oos_start,oos_end,universe_version,dataset_version,
                 adjustment_contract,feature_pipeline_version,fold_fingerprint,oos_input_fingerprint,
                 status,created_at)
            values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                window_id,
                run_id,
                batch_id,
                group["projectId"],
                group["symbol"],
                group["fold"],
                train["start"],
                train["end"],
                validation["start"],
                validation["end"],
                oos["start"],
                oos["end"],
                str(config["universeVersion"]),
                str(config["datasetVersion"]),
                str(config["adjustmentContract"]),
                str(config["featurePipelineVersion"]),
                fold_fingerprint,
                _digest(base_oos_input),
                "VALIDATION_PENDING",
                now,
            ),
        )
        connection.execute(
            """
            insert into feature_pipeline_fits
                (id,window_id,pipeline_version,fit_phase,fit_start,fit_end,fit_statistics_json,
                 fit_fingerprint,created_at)
            values (?,?,?,?,?,?,?,?,?)
            """,
            (
                str(uuid.uuid4()),
                window_id,
                str(config["featurePipelineVersion"]),
                "TRAIN",
                train["start"],
                train["end"],
                json_dump({"scope": "train_only", "status": "pending"}),
                _digest(
                    {
                        "windowId": window_id,
                        "pipelineVersion": config["featurePipelineVersion"],
                        "fitStart": train["start"],
                        "fitEnd": train["end"],
                    }
                ),
                now,
            ),
        )
        connection.execute(
            """
            insert into leakage_check_results
                (id,window_id,decision,check_version,result_json,checked_at)
            values (?,?,?,?,?,?)
            """,
            (
                str(uuid.uuid4()),
                window_id,
                leakage["decision"],
                leakage["checkVersion"],
                json_dump(leakage),
                now,
            ),
        )
        for candidate_key, candidate_phases in group["candidates"].items():
            validation_item = candidate_phases["validation"]
            candidate_parameters = (
                validation_item.get("parameters", {}).get("parameters", {}).get("optimizationOverrides")
                or {}
            )
            connection.execute(
                """
                insert into parameter_candidates
                    (id,window_id,candidate_key,parameters_json,train_item_id,validation_item_id,
                     created_at,updated_at)
                values (?,?,?,?,?,?,?,?)
                """,
                (
                    str(uuid.uuid5(uuid.NAMESPACE_URL, f"{window_id}:{candidate_key}")),
                    window_id,
                    candidate_key,
                    json_dump(candidate_parameters),
                    item_ids[candidate_phases["train"]["key"]],
                    item_ids[validation_item["key"]],
                    now,
                    now,
                ),
            )


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
    item_ids = {item["key"]: str(uuid.uuid4()) for item in items}
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
            values (?,?,?,?,?,?,?,?,?)
            """,
            [
                (
                    item_ids[item["key"]],
                    batch_id,
                    index,
                    item["key"],
                    item.get("projectId"),
                    item.get("symbol"),
                    (
                        SELECTION_BLOCKED
                        if str(config.get("mode") or "") == "walk_forward"
                        and str((item["parameters"].get("parameters") or {}).get("experimentPhase")) == "oos"
                        else "pending"
                    ),
                    json_dump(item["parameters"]),
                    now,
                )
                for index, item in enumerate(items, start=1)
            ],
        )
        _persist_walk_forward_plan(
            connection,
            batch_id=batch_id,
            config=config,
            items=items,
            item_ids=item_ids,
            now=now,
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


def _numeric_overrides(items: list[dict[str, Any]]) -> list[str]:
    keys: set[str] = set()
    for item in items:
        for key, value in (item.get("overrides") or {}).items():
            if _number(value) is not None:
                keys.add(str(key))
    return sorted(keys)


def _parameter_sensitivity(
    ranked: list[dict[str, Any]],
    *,
    metric: str = "sharpe",
    x_parameter: str | None = None,
    y_parameter: str | None = None,
) -> list[dict[str, Any]]:
    numeric_keys = _numeric_overrides(ranked)
    if len(numeric_keys) < 2:
        return []
    x_key = x_parameter if x_parameter in numeric_keys else numeric_keys[0]
    y_key = y_parameter if y_parameter in numeric_keys and y_parameter != x_key else next(
        key for key in numeric_keys if key != x_key
    )
    grouped: dict[tuple[float, float], list[float]] = {}
    for item in ranked:
        if item.get("status") != "success":
            continue
        overrides = item.get("overrides") or {}
        x_value = _number(overrides.get(x_key))
        y_value = _number(overrides.get(y_key))
        metric_value = _number(item.get(metric))
        if x_value is None or y_value is None or metric_value is None:
            continue
        grouped.setdefault((x_value, y_value), []).append(metric_value)
    if not grouped:
        return []
    cells = [
        {
            "x": x_value,
            "y": y_value,
            "value": sum(values) / len(values),
            "median": stats_module.median(values),
            "count": len(values),
        }
        for (x_value, y_value), values in sorted(grouped.items())
    ]
    return [
        {
            "metric": metric,
            "xParameter": x_key,
            "yParameter": y_key,
            "xValues": sorted({cell["x"] for cell in cells}),
            "yValues": sorted({cell["y"] for cell in cells}),
            "cells": cells,
        }
    ]


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
    folds = sorted(
        {
            int(item["fold"])
            for item in ranked
            if item.get("phase") == "validation" and item.get("fold") is not None
        }
    )
    for fold in folds:
        validation = [
            item
            for item in ranked
            if item.get("fold") == fold
            and item.get("phase") == "validation"
            and item.get("status") == "success"
            and item.get("sharpe") is not None
        ]
        selected = max(validation, key=lambda item: float(item["sharpe"]), default=None)
        if not selected:
            continue

        def selected_phase(phase: str) -> dict[str, Any] | None:
            return next(
                (
                    item
                    for item in ranked
                    if item.get("fold") == fold
                    and item.get("phase") == phase
                    and item.get("projectId") == selected.get("projectId")
                    and item.get("symbol") == selected.get("symbol")
                    and item.get("candidateKey") == selected.get("candidateKey")
                ),
                None,
            )

        train = selected_phase("train")
        oos = selected_phase("oos")
        walk_forward.append(
            {
                "fold": fold,
                "selectionMetric": "validationSharpe",
                "selected": selected.get("overrides"),
                "trainSharpe": train.get("sharpe") if train else None,
                "validationSharpe": selected.get("sharpe"),
                "oosSharpe": oos.get("sharpe") if oos else None,
                "trainRunId": train.get("runId") if train else None,
                "validationRunId": selected.get("runId"),
                "oosRunId": oos.get("runId") if oos else None,
            }
        )
    return {
        "rankingMetric": "sharpe",
        "ranking": ranked,
        "candidates": candidates,
        "parameterSensitivity": _parameter_sensitivity(ranked),
        "walkForward": walk_forward,
    }


def _aggregate_batch_metrics(ranking: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [item for item in ranking if item.get("status") == "success"]
    result: dict[str, Any] = {"runs": len(ranking), "successes": len(successful)}
    for metric in ("sharpe", "return", "drawdown", "trades"):
        values = [
            number
            for item in successful
            if (number := _number(item.get(metric))) is not None
        ]
        result[metric] = {
            "best": (
                min(values, key=abs)
                if metric == "drawdown" and values
                else max(values)
                if values
                else None
            ),
            "median": stats_module.median(values) if values else None,
            "mean": sum(values) / len(values) if values else None,
            "count": len(values),
        }
    return result


def compare_batches(
    batch_ids: list[str],
    *,
    metric: str = "sharpe",
    x_parameter: str | None = None,
    y_parameter: str | None = None,
) -> dict[str, Any]:
    ids = list(dict.fromkeys(str(value).strip() for value in batch_ids if str(value).strip()))
    if not 2 <= len(ids) <= 10:
        raise LeanWebError("Compare between 2 and 10 unique experiment batches.")
    metric_key = str(metric or "sharpe").strip()
    if metric_key not in {"sharpe", "return", "drawdown", "trades"}:
        raise LeanWebError("metric must be sharpe, return, drawdown, or trades.")
    compared = []
    for batch_id in ids:
        batch = detail(batch_id)
        summary = batch.get("summary") or {}
        ranking = list(summary.get("ranking") or [])
        aggregate = _aggregate_batch_metrics(ranking)
        sensitivity = _parameter_sensitivity(
            ranking,
            metric=metric_key,
            x_parameter=x_parameter,
            y_parameter=y_parameter,
        )
        compared.append(
            {
                "id": batch["id"],
                "name": batch["name"],
                "kind": batch["kind"],
                "mode": batch["mode"],
                "status": batch["status"],
                "createdAt": batch["created_at"],
                "metrics": aggregate,
                "bestRun": next(
                    (
                        item
                        for item in sorted(
                            ranking,
                            key=lambda row: (
                                abs(_number(row.get(metric_key)) or 0)
                                if metric_key == "drawdown" and _number(row.get(metric_key)) is not None
                                else _number(row.get(metric_key))
                                if _number(row.get(metric_key)) is not None
                                else float("-inf")
                            ),
                            reverse=metric_key != "drawdown",
                        )
                        if item.get("status") == "success" and _number(item.get(metric_key)) is not None
                    ),
                    None,
                ),
                "parameterSensitivity": sensitivity,
                "phaseSeries": summary.get("walkForward") or [],
            }
        )
    def score(item: dict[str, Any]) -> float:
        value = item["metrics"].get(metric_key, {}).get("median")
        if value is None:
            return float("-inf")
        return -abs(float(value)) if metric_key == "drawdown" else float(value)

    compared.sort(key=score, reverse=True)
    for index, item in enumerate(compared, start=1):
        item["rank"] = index
        item["rankingValue"] = item["metrics"].get(metric_key, {}).get("median")
    return {
        "rankingMetric": metric_key,
        "rankingBasis": "median successful run",
        "batches": compared,
        "metricMatrix": [
            {
                "metric": metric_name,
                "values": {
                    item["id"]: item["metrics"].get(metric_name, {})
                    for item in compared
                },
            }
            for metric_name in ("sharpe", "return", "drawdown", "trades")
        ],
    }


def _walk_forward_item_groups(items: list[dict[str, Any]]) -> dict[tuple[str, str, int], dict[str, list[dict[str, Any]]]]:
    groups: dict[tuple[str, str, int], dict[str, list[dict[str, Any]]]] = {}
    for item in items:
        request = item.get("parameters") or {}
        parameters = request.get("parameters") or {}
        fold = parameters.get("experimentFold")
        phase = str(parameters.get("experimentPhase") or "")
        if fold is None or phase not in {"train", "validation", "oos"}:
            continue
        key = (str(item.get("project_id") or ""), str(item.get("symbol") or ""), int(fold))
        groups.setdefault(key, {"train": [], "validation": [], "oos": []})[phase].append(item)
    return groups


def _validation_metrics(item: dict[str, Any]) -> dict[str, Any]:
    statistics = (item.get("result") or {}).get("statistics") or {}
    return {
        "return": _number(_metric(statistics, "Net Profit", "Compounding Annual Return", "Total Return")),
        "sharpe": _number(_metric(statistics, "Sharpe Ratio", "Sharpe")),
        "drawdown": _number(_metric(statistics, "Drawdown", "Maximum Drawdown")),
        "trades": _number(_metric(statistics, "Total Orders", "Total Trades")),
        "turnover": _number(_metric(statistics, "Portfolio Turnover", "Turnover")),
        "constraintViolations": int(
            _number(_metric(statistics, "Constraint Violations", "ConstraintViolations")) or 0
        ),
    }


def _advance_walk_forward_selection(batch: dict[str, Any], items: list[dict[str, Any]]) -> bool:
    if str(batch.get("mode") or "") != "walk_forward" or batch.get("cancel_requested"):
        return False
    changed = False
    now = utc_now()
    for (project_id, symbol, fold), phases in _walk_forward_item_groups(items).items():
        validation_items = phases["validation"]
        if not validation_items or any(item["status"] not in TERMINAL for item in validation_items):
            continue
        if any(item["status"] != "success" for item in validation_items):
            continue
        ranked: list[dict[str, Any]] = []
        for item in validation_items:
            parameters = (item.get("parameters") or {}).get("parameters") or {}
            metrics = _validation_metrics(item)
            if metrics["sharpe"] is None:
                continue
            ranked.append(
                {
                    "item": item,
                    "candidateKey": str(parameters.get("optimizationCandidateKey") or "base"),
                    "parameters": parameters.get("optimizationOverrides") or {},
                    **metrics,
                }
            )
        if len(ranked) != len(validation_items):
            continue
        ranked.sort(
            key=lambda row: (
                -float(row["sharpe"]),
                abs(float(row["drawdown"] or 0.0)),
                float(row["turnover"] or 0.0),
                row["candidateKey"],
            )
        )
        selected = ranked[0]
        with db() as connection:
            window = connection.execute(
                """
                select * from walk_forward_windows
                where batch_id=? and project_id=? and symbol=? and fold=?
                """,
                (batch["id"], project_id, symbol, fold),
            ).fetchone()
            if not window:
                continue
            existing = connection.execute(
                "select id from parameter_selection_events where window_id=?",
                (window["id"],),
            ).fetchone()
            if existing:
                continue
            candidates = connection.execute(
                "select * from parameter_candidates where window_id=?",
                (window["id"],),
            ).fetchall()
            by_key = {str(row["candidate_key"]): row for row in candidates}
            for rank, row in enumerate(ranked, start=1):
                candidate = by_key[row["candidateKey"]]
                connection.execute(
                    """
                    update parameter_candidates
                    set validation_return=?,validation_sharpe=?,validation_max_drawdown=?,
                        validation_trade_count=?,validation_turnover=?,constraint_violations=?,
                        selected=?,not_selected_reason=?,updated_at=?
                    where id=?
                    """,
                    (
                        row["return"],
                        row["sharpe"],
                        row["drawdown"],
                        int(row["trades"]) if row["trades"] is not None else None,
                        row["turnover"],
                        row["constraintViolations"],
                        1 if rank == 1 else 0,
                        None if rank == 1 else f"validation_rank_{rank}",
                        now,
                        candidate["id"],
                    ),
                )
            selected_candidate = by_key[selected["candidateKey"]]
            ranking_payload = [
                {
                    key: value
                    for key, value in row.items()
                    if key not in {"item"}
                }
                for row in ranked
            ]
            selection_fingerprint = _digest(
                {
                    "windowId": window["id"],
                    "metric": "validationSharpe",
                    "tieBreak": "minDrawdown,minTurnover,candidateKey",
                    "ranking": ranking_payload,
                }
            )
            connection.execute(
                """
                insert into parameter_selection_events
                    (id,window_id,selected_candidate_id,selection_metric,tie_break_rule,
                     selected_parameters_json,candidate_ranking_json,selection_timestamp,
                     selection_fingerprint)
                values (?,?,?,?,?,?,?,?,?)
                """,
                (
                    str(uuid.uuid4()),
                    window["id"],
                    selected_candidate["id"],
                    "validationSharpe",
                    "minDrawdown,minTurnover,candidateKey",
                    json_dump(selected["parameters"]),
                    json_dump(ranking_payload),
                    now,
                    selection_fingerprint,
                ),
            )
            selected_oos: dict[str, Any] | None = None
            for oos_item in phases["oos"]:
                parameters = (oos_item.get("parameters") or {}).get("parameters") or {}
                candidate_key = str(parameters.get("optimizationCandidateKey") or "base")
                if candidate_key == selected["candidateKey"]:
                    selected_oos = oos_item
                    connection.execute(
                        """
                        update experiment_batch_items
                        set status='pending',error=null,finished_at=null
                        where id=? and status=?
                        """,
                        (oos_item["id"], SELECTION_BLOCKED),
                    )
                else:
                    connection.execute(
                        """
                        update experiment_batch_items
                        set status='skipped',error='not_selected_by_validation',finished_at=?
                        where id=? and status=?
                        """,
                        (now, oos_item["id"], SELECTION_BLOCKED),
                    )
            if selected_oos is None:
                raise LeanWebError(f"Selected candidate has no OOS item for fold {fold}.")
            oos_input_fingerprint = _digest(
                {
                    "baseFingerprint": window["oos_input_fingerprint"],
                    "selectionFingerprint": selection_fingerprint,
                    "selectedParameters": selected["parameters"],
                }
            )
            connection.execute(
                """
                update walk_forward_windows
                set status='PARAMETER_FROZEN',oos_input_fingerprint=?
                where id=?
                """,
                (oos_input_fingerprint, window["id"]),
            )
            connection.execute(
                """
                insert into oos_evaluations
                    (id,window_id,selected_candidate_id,oos_item_id,input_fingerprint,status,created_at)
                values (?,?,?,?,?,'PENDING',?)
                """,
                (
                    str(uuid.uuid4()),
                    window["id"],
                    selected_candidate["id"],
                    selected_oos["id"],
                    oos_input_fingerprint,
                    now,
                ),
            )
            connection.execute(
                "update walk_forward_runs set status='OOS_PENDING' where batch_id=?",
                (batch["id"],),
            )
        changed = True
    return changed


def _persist_oos_evaluation(item_id: str, run_id: str, status: str, result: dict[str, Any]) -> None:
    now = utc_now()
    result_digest = _digest(result) if status == "success" else None
    with db() as connection:
        evaluation = connection.execute(
            "select id,window_id from oos_evaluations where oos_item_id=?",
            (item_id,),
        ).fetchone()
        if not evaluation:
            return
        connection.execute(
            """
            update oos_evaluations
            set oos_run_id=?,result_digest=?,metrics_json=?,status=?,completed_at=?
            where id=?
            """,
            (
                run_id,
                result_digest,
                json_dump(result),
                "COMPLETED" if status == "success" else "FAILED",
                now,
                evaluation["id"],
            ),
        )
        connection.execute(
            """
            update walk_forward_windows
            set status=?,completed_at=?
            where id=?
            """,
            (
                "OOS_COMPLETED" if status == "success" else "OOS_FAILED",
                now,
                evaluation["window_id"],
            ),
        )


def refresh(batch_id: str) -> dict[str, Any]:
    with db() as connection:
        item_rows = connection.execute("select * from experiment_batch_items where batch_id=? order by item_index", (batch_id,)).fetchall()
        batch_row = connection.execute("select * from experiment_batches where id=?", (batch_id,)).fetchone()
    if not batch_row:
        raise NotFoundError("Experiment batch not found.")
    items = rows_to_dicts(item_rows)
    if _advance_walk_forward_selection(dict(batch_row), items):
        with db() as connection:
            item_rows = connection.execute(
                "select * from experiment_batch_items where batch_id=? order by item_index",
                (batch_id,),
            ).fetchall()
        items = rows_to_dicts(item_rows)
    counts = {key: sum(1 for item in items if item["status"] == key) for key in ("pending", "dispatching", "queued", "running", "success", "failed", "skipped", "cancelled", SELECTION_BLOCKED)}
    selection_skips = sum(
        1
        for item in items
        if item["status"] == "skipped" and item.get("error") == "not_selected_by_validation"
    )
    blocking_skips = counts["skipped"] - selection_skips
    completed = counts["success"] + counts["failed"] + counts["skipped"] + counts["cancelled"]
    active = counts["dispatching"] + counts["queued"] + counts["running"]
    cancel_requested = bool(batch_row["cancel_requested"])
    if completed == len(items):
        status = "cancelled" if cancel_requested and not counts["success"] else "partial" if counts["failed"] or blocking_skips or counts["cancelled"] else "success"
        finished_at = batch_row["finished_at"] or utc_now()
    elif counts["failed"] and not active and not counts["pending"]:
        status = "partial"
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
            (status, json_dump(summary), counts["pending"] + counts["dispatching"] + counts["queued"] + counts[SELECTION_BLOCKED], counts["running"], counts["success"], counts["failed"], counts["skipped"], counts["cancelled"], status, utc_now(), finished_at, batch_id),
        )
        if status in TERMINAL | {"partial"}:
            connection.execute(
                """
                update walk_forward_runs
                set status=?,completed_at=?
                where batch_id=?
                """,
                (
                    "COMPLETED" if status == "success" else "FAILED",
                    finished_at,
                    batch_id,
                ),
            )
    return detail(batch_id, refresh_state=False)


def detail(batch_id: str, *, refresh_state: bool = True) -> dict[str, Any]:
    if refresh_state:
        return refresh(batch_id)
    with db() as connection:
        row = connection.execute("select * from experiment_batches where id=?", (batch_id,)).fetchone()
        items = connection.execute("select * from experiment_batch_items where batch_id=? order by item_index", (batch_id,)).fetchall()
        walk_forward_run = connection.execute(
            "select * from walk_forward_runs where batch_id=?",
            (batch_id,),
        ).fetchone()
        windows = connection.execute(
            "select * from walk_forward_windows where batch_id=? order by fold,project_id,symbol",
            (batch_id,),
        ).fetchall()
    batch = row_to_dict(row)
    if batch is None:
        raise NotFoundError("Experiment batch not found.")
    batch["items"] = rows_to_dicts(items)
    if walk_forward_run:
        evidence = row_to_dict(walk_forward_run) or {}
        evidence["windows"] = []
        with db() as connection:
            for window in rows_to_dicts(windows):
                candidates = connection.execute(
                    "select * from parameter_candidates where window_id=? order by selected desc,candidate_key",
                    (window["id"],),
                ).fetchall()
                selection = connection.execute(
                    "select * from parameter_selection_events where window_id=?",
                    (window["id"],),
                ).fetchone()
                leakage = connection.execute(
                    "select * from leakage_check_results where window_id=? order by checked_at desc limit 1",
                    (window["id"],),
                ).fetchone()
                oos = connection.execute(
                    "select * from oos_evaluations where window_id=?",
                    (window["id"],),
                ).fetchone()
                window["candidates"] = rows_to_dicts(candidates)
                window["selection"] = row_to_dict(selection)
                window["leakage"] = row_to_dict(leakage)
                window["oosEvaluation"] = row_to_dict(oos)
                evidence["windows"].append(window)
        batch["walkForwardEvidence"] = evidence
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
            connection.execute(
                """
                insert into experiment_batch_attempts
                    (id,item_id,attempt,related_id,task_id,status,error,created_at,finished_at)
                values (?,?,?,?,?,'failed',?,?,?)
                """,
                (
                    str(uuid.uuid4()),
                    item["id"],
                    attempt,
                    run.get("id"),
                    run.get("task_id"),
                    str(exc),
                    utc_now(),
                    utc_now(),
                ),
            )
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
    _persist_oos_evaluation(run["batch_item_id"], run_id, item_status, result)
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
    now = utc_now()
    with db() as connection:
        connection.execute("update experiment_batches set cancel_requested=1 where id=?", (batch_id,))
        connection.execute(
            """
            update experiment_batch_items
            set status='cancelled',finished_at=?
            where batch_id=? and status in ('pending','dispatching','queued','blocked_selection')
            """,
            (now, batch_id),
        )
        cancelled_attempts = connection.execute(
            """
            select id,attempt from experiment_batch_items
            where batch_id=? and status='cancelled' and attempt > 0
            """,
            (batch_id,),
        ).fetchall()
        for item in cancelled_attempts:
            connection.execute(
                """
                update experiment_batch_attempts
                set status='cancelled',finished_at=?
                where item_id=? and attempt=? and status not in ('success','failed','cancelled')
                """,
                (now, item["id"], item["attempt"]),
            )
    for item in batch["items"]:
        if item["status"] in ACTIVE and item.get("related_id"):
            cancel_backtest(str(item["related_id"]))
    return refresh(batch_id)


def retry_failed(batch_id: str) -> dict[str, Any]:
    batch = detail(batch_id)
    if batch["status"] not in TERMINAL | {"partial"}:
        raise LeanWebError("Only a completed batch can retry failed items.")
    failed_ids = [item["id"] for item in batch["items"] if item["status"] == "failed"]
    if not failed_ids:
        raise LeanWebError("The batch has no failed items to retry.")
    with db() as connection:
        connection.execute("update experiment_batches set status='queued',cancel_requested=0,finished_at=null where id=?", (batch_id,))
        connection.execute(
            """
            update experiment_batch_items
            set status='pending',related_id=null,task_id=null,error=null,started_at=null,finished_at=null
            where batch_id=? and status='failed'
            """,
            (batch_id,),
        )
    return dispatch_window(batch_id)


def restart_cancelled(batch_id: str) -> dict[str, Any]:
    batch = detail(batch_id)
    if not batch.get("cancel_requested") or batch["status"] not in TERMINAL | {"partial"}:
        raise LeanWebError("Only a completed cancelled batch can be restarted.")
    restartable = [
        item["id"]
        for item in batch["items"]
        if item["status"] in {"cancelled", "failed", "skipped"}
    ]
    if not restartable:
        raise LeanWebError("The cancelled batch has no unfinished items to restart.")
    with db() as connection:
        connection.execute(
            """
            update experiment_batches
            set status='queued',cancel_requested=0,finished_at=null
            where id=?
            """,
            (batch_id,),
        )
        connection.execute(
            """
            update experiment_batch_items
            set status='pending',related_id=null,task_id=null,error=null,started_at=null,finished_at=null
            where batch_id=? and status in ('cancelled','failed','skipped')
            """,
            (batch_id,),
        )
    return dispatch_window(batch_id)


def export_csv(batch_id: str) -> str:
    batch = detail(batch_id)
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "item",
            "projectId",
            "symbol",
            "fold",
            "phase",
            "candidateKey",
            "selected",
            "status",
            "runId",
            "sharpe",
            "return",
            "drawdown",
            "trades",
            "error",
        ],
    )
    writer.writeheader()
    ranking = {item["itemId"]: item for item in (batch.get("summary") or {}).get("ranking", [])}
    selected_candidates = {
        (
            str(window.get("project_id") or ""),
            str(window.get("symbol") or ""),
            int(window.get("fold") or 0),
        ): str((window.get("selection") or {}).get("selected_candidate_id") or "")
        for window in (batch.get("walkForwardEvidence") or {}).get("windows", [])
    }
    candidate_ids = {
        (
            str(window.get("project_id") or ""),
            str(window.get("symbol") or ""),
            int(window.get("fold") or 0),
            str(candidate.get("candidate_key") or ""),
        ): str(candidate.get("id") or "")
        for window in (batch.get("walkForwardEvidence") or {}).get("windows", [])
        for candidate in window.get("candidates") or []
    }
    for item in batch["items"]:
        metrics = ranking.get(item["id"], {})
        fold = int(metrics.get("fold") or 0)
        candidate_key = str(metrics.get("candidateKey") or "")
        candidate_id = candidate_ids.get(
            (str(item.get("project_id") or ""), str(item.get("symbol") or ""), fold, candidate_key)
        )
        writer.writerow(
            {
                "item": item["item_key"],
                "projectId": item.get("project_id"),
                "symbol": item.get("symbol"),
                "fold": metrics.get("fold"),
                "phase": metrics.get("phase"),
                "candidateKey": candidate_key,
                "selected": candidate_id
                == selected_candidates.get(
                    (str(item.get("project_id") or ""), str(item.get("symbol") or ""), fold)
                ),
                "status": item["status"],
                "runId": item.get("related_id"),
                "sharpe": metrics.get("sharpe"),
                "return": metrics.get("return"),
                "drawdown": metrics.get("drawdown"),
                "trades": metrics.get("trades"),
                "error": item.get("error"),
            }
        )
    return output.getvalue()
