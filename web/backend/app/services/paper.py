import hashlib
import json
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

from ..core.config import RUNS_DIR
from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now
from ..domain.assets import asset_request
from ..lean_engine.errors import LeanPlatformError
from ..lean_engine.symbols import market_key, normalize_symbol, parse_date
from ..repositories.backtest_repository import get_backtest, get_result
from .ashare_repository import is_tradeable
from .ashare_multisource import quality_gate
from .backtest_service import create_backtest_job, mark_backtest_queued
from .data_coverage import ashare_coverage
from .experiments import get_experiment_versions
from .source_gate import apply_source_context, resolve_source_context
from .trading_config import ashare_trading_config
from .run_paths import run_directory


def _side(value: str) -> str:
    side = value.strip().lower()
    if side not in {"buy", "sell", "hold"}:
        raise ValueError("Signal side must be buy, sell, or hold.")
    return side


def list_sessions() -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute("select * from paper_sessions order by created_at desc").fetchall()
    return [_session_api_item(item) for item in rows_to_dicts(rows)]


def get_session(session_id: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute("select * from paper_sessions where id = ?", (session_id,)).fetchone()
    item = row_to_dict(row)
    return _session_api_item(item) if item else None


def _session_api_item(item: dict[str, Any]) -> dict[str, Any]:
    item["mode"] = item.get("mode") or "legacy_replay"
    item["legacy_read_only"] = bool(item.get("legacy_read_only", item["mode"] == "legacy_replay"))
    item["auto_advance"] = bool(item.get("auto_advance"))
    if item["mode"] == "lean_walkforward":
        item["next_trade_date"] = (
            _next_china_trade_date(str(item["last_processed_date"]))
            if item.get("last_processed_date")
            else item.get("start_date")
        )
    return item


def list_walkforward_runs(session_id: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            "select * from paper_walkforward_runs where session_id = ? order by trade_date desc",
            (session_id,),
        ).fetchall()
    return rows_to_dicts(rows)


def get_walkforward_run(paper_run_id: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute(
            "select * from paper_walkforward_runs where id = ?",
            (paper_run_id,),
        ).fetchone()
    return row_to_dict(row)


def trusted_backtest_candidates(project_id: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            """
            select br.*, experiment.strategy_version_id, experiment.parameter_hash,
                   (
                       select admission.current_stage
                       from strategy_admissions admission
                       where admission.strategy_id = br.project_id
                         and admission.parameters_sha256 = experiment.parameter_hash
                         and admission.profile_name = 'institutional'
                       order by admission.updated_at desc
                       limit 1
                   ) as admission_stage
            from backtest_runs br
            left join experiments experiment on experiment.run_id = br.id
            where br.project_id = ? and br.status = 'success'
            order by br.finished_at desc, br.created_at desc
            """,
            (project_id,),
        ).fetchall()
    candidates = []
    for raw in rows:
        item = row_to_dict(raw) or {}
        validation = item.get("validation") or {}
        parameters = item.get("parameters") or {}
        snapshot = run_directory(str(item["id"]), parameters.get("strategySnapshotDir"), relative="strategy")
        if validation.get("passed") is not True or not snapshot.is_dir() or not get_result(str(item["id"])):
            continue
        data_validation = validation.get("data") or {}
        if data_validation.get("truncated") is True or parameters.get("allowTruncatedData"):
            continue
        candidates.append(
            {
                "id": item["id"],
                "name": item.get("name"),
                "symbol": item.get("symbol"),
                "start": parameters.get("start"),
                "end": parameters.get("end"),
                "cash": parameters.get("cash"),
                "finishedAt": item.get("finished_at"),
                "strategyVersionId": item.get("strategy_version_id"),
                "parameterHash": item.get("parameter_hash"),
                "admissionStage": item.get("admission_stage"),
                "validation": validation,
            }
        )
    return candidates


def _next_china_trade_date(value: str) -> str:
    current = parse_date(value)
    with db() as connection:
        row = connection.execute(
            """
            select trade_date from trade_calendar
            where market = 'china' and is_open = 1 and trade_date > ?
            order by trade_date asc limit 1
            """,
            (current.isoformat(),),
        ).fetchone()
    if row:
        return str(row["trade_date"])
    candidate = current + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate.isoformat()


def _create_lean_session(parameters: dict[str, Any]) -> dict[str, Any]:
    project_id = str(parameters.get("projectId") or "").strip()
    source_backtest_id = str(parameters.get("sourceBacktestId") or "").strip()
    if not project_id or not source_backtest_id:
        raise ValueError("LEAN Paper requires projectId and sourceBacktestId.")
    source_run = get_backtest(source_backtest_id)
    if not source_run or source_run.get("project_id") != project_id:
        raise ValueError("The selected backtest does not belong to this project.")
    if source_run.get("status") != "success" or (source_run.get("validation") or {}).get("passed") is not True:
        raise ValueError("The selected backtest has not passed execution validation.")
    if not get_result(source_backtest_id):
        raise ValueError("The selected backtest result ledger is unavailable.")
    source_parameters = dict(source_run.get("parameters") or {})
    snapshot_dir = run_directory(source_backtest_id, source_parameters.get("strategySnapshotDir"), relative="strategy")
    if not snapshot_dir.is_dir():
        raise ValueError("The selected backtest strategy snapshot is unavailable.")
    if source_parameters.get("allowTruncatedData") or ((source_run.get("validation") or {}).get("data") or {}).get("truncated"):
        raise ValueError("Truncated backtests cannot seed LEAN Paper.")
    versions = get_experiment_versions(source_backtest_id) or {}
    experiment = versions.get("experiment") or {}
    request = asset_request(
        str(source_run["symbol"]),
        str(source_run.get("asset_class") or source_parameters.get("assetClass") or "equity"),
        venue=str(source_run.get("venue") or source_parameters.get("venue") or source_parameters.get("market") or "china"),
        market=str(source_parameters.get("market") or source_run.get("venue") or "china"),
        resolution=str(source_run.get("resolution") or source_parameters.get("resolution") or "daily"),
        data_type=str(source_run.get("data_type") or source_parameters.get("dataType") or "trade"),
    )
    if request.asset_class != "equity" or request.venue != "china" or request.resolution != "daily":
        raise ValueError("LEAN Paper currently supports China A-share daily projects only.")
    cash = float(source_parameters.get("cash") or source_parameters.get("initialCash") or 100000)
    start_date = str(parameters.get("startDate") or _next_china_trade_date(str(source_parameters["end"])))
    if parse_date(start_date) <= parse_date(str(source_parameters["end"])):
        raise ValueError("Paper startDate must be after the source backtest end date.")
    session_id = str(uuid.uuid4())
    now = utc_now()
    frozen = {
        **source_parameters,
        "sourceBacktestId": source_backtest_id,
        "strategySnapshotDir": str(snapshot_dir),
        "strategySnapshotMainFile": source_parameters.get("strategySnapshotMainFile"),
        "strategySnapshotAlgorithmClass": source_parameters.get("strategySnapshotAlgorithmClass"),
        "strategySnapshotLanguage": source_parameters.get("strategySnapshotLanguage"),
    }
    with db() as connection:
        connection.execute(
            """
            insert into paper_sessions
                (id, project_id, name, status, symbol, asset_class, venue, resolution, cash, equity,
                 parameters_json, created_at, updated_at, mode, legacy_read_only, source_backtest_id,
                 strategy_version_id, parameter_hash, start_date, auto_advance)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                project_id,
                parameters.get("name") or f"{request.symbol} LEAN Paper",
                "created",
                request.symbol,
                request.asset_class,
                request.venue,
                request.resolution,
                cash,
                cash,
                json_dump(frozen),
                now,
                now,
                "lean_walkforward",
                0,
                source_backtest_id,
                experiment.get("strategy_version_id"),
                experiment.get("parameter_hash"),
                start_date,
                1 if parameters.get("autoAdvance", True) else 0,
            ),
        )
    return get_session(session_id) or {}


def list_signals(session_id: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            "select * from paper_signals where session_id = ? order by trade_date asc, created_at asc",
            (session_id,),
        ).fetchall()
    return rows_to_dicts(rows)


def list_orders(session_id: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            "select * from paper_orders where session_id = ? order by trade_date asc, created_at asc",
            (session_id,),
        ).fetchall()
    return rows_to_dicts(rows)


def list_positions(session_id: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute("select * from paper_positions where session_id = ? order by symbol", (session_id,)).fetchall()
    return rows_to_dicts(rows)


def list_snapshots(session_id: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            "select * from paper_portfolio_snapshots where session_id = ? order by trade_date asc",
            (session_id,),
        ).fetchall()
    return rows_to_dicts(rows)


def list_daily_reports(session_id: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            "select * from paper_daily_reports where session_id = ? order by trade_date asc",
            (session_id,),
        ).fetchall()
    return [_daily_report_api_item(item) for item in rows_to_dicts(rows)]


def get_daily_report(session_id: str, trade_date: str) -> dict[str, Any] | None:
    date_value = parse_date(trade_date).isoformat()
    with db() as connection:
        row = connection.execute(
            "select * from paper_daily_reports where session_id = ? and trade_date = ?",
            (session_id, date_value),
        ).fetchone()
    item = row_to_dict(row)
    return _daily_report_api_item(item) if item else None


def _daily_report_api_item(item: dict[str, Any]) -> dict[str, Any]:
    report = item.get("report") or {}
    report.setdefault("schemaVersion", 1)
    for key in (
        "schemaVersion",
        "sessionId",
        "tradeDate",
        "strategy",
        "executionPolicy",
        "initialCash",
        "cash",
        "NAV",
        "nav",
        "dailyReturn",
        "cumulativeReturn",
        "excessReturn",
        "rejectionReasons",
        "positionWeights",
        "dataSourceStatus",
        "coverageSummary",
        "warnings",
        "fingerprint",
        "signals",
        "pendingSignals",
        "executionSignals",
        "orders",
        "trades",
        "rejects",
        "positions",
        "snapshot",
        "benchmark",
        "qa",
    ):
        if key in report and key not in item:
            item[key] = report[key]
    if "pendingSignals" not in item:
        item["pendingSignals"] = report.get("pendingSignals") or report.get("executionSignals") or []
    if "executionSignals" not in item:
        item["executionSignals"] = item["pendingSignals"]
    if "rejectedOrders" not in item:
        item["rejectedOrders"] = item.get("rejects") or report.get("rejects") or []
    if "rejectReasons" not in item:
        item["rejectReasons"] = item.get("rejectionReasons") or report.get("rejectionReasons") or []
    benchmark = item.get("benchmark") or {}
    if "benchmarkSymbol" not in item:
        item["benchmarkSymbol"] = benchmark.get("symbol")
    if "benchmarkClose" not in item:
        item["benchmarkClose"] = benchmark.get("close")
    if "benchmarkReturn" not in item:
        item["benchmarkReturn"] = benchmark.get("return")
    qa = item.get("qa") or {}
    if "qaGateStatus" not in item:
        item["qaGateStatus"] = qa.get("severity")
    return item


def create_session(parameters: dict[str, Any]) -> dict[str, Any]:
    if parameters.get("sourceBacktestId") or parameters.get("mode") == "lean_walkforward":
        return _create_lean_session(parameters)
    raw_symbols = parameters.get("symbols") or parameters.get("paperSymbols") or []
    if isinstance(raw_symbols, str):
        raw_symbols = [item.strip() for item in raw_symbols.split(",") if item.strip()]
    if raw_symbols:
        primary_symbol = raw_symbols[0]
    else:
        primary_symbol = parameters["symbol"]
    request = asset_request(
        primary_symbol,
        parameters.get("assetClass", "equity"),
        venue=parameters.get("venue"),
        market=parameters.get("market"),
        resolution=parameters.get("resolution", "daily"),
        data_type=parameters.get("dataType", "trade"),
    )
    cash = float(parameters.get("cash", 100000))
    session_id = str(uuid.uuid4())
    now = utc_now()
    name = parameters.get("name") or f"{request.symbol} Paper Replay"
    nested_parameters = parameters.get("parameters") if isinstance(parameters.get("parameters"), dict) else {}
    clean = {
        **nested_parameters,
        **parameters,
        "symbol": request.symbol,
        "symbols": [
            asset_request(
                symbol,
                parameters.get("assetClass", "equity"),
                venue=parameters.get("venue"),
                market=parameters.get("market"),
                resolution=parameters.get("resolution", "daily"),
                data_type=parameters.get("dataType", "trade"),
            ).symbol
            for symbol in (raw_symbols or [request.symbol])
        ],
        "assetClass": request.asset_class,
        "venue": request.venue,
        "resolution": request.resolution,
        "dataType": request.data_type,
        "cash": cash,
    }
    if request.asset_class == "equity" and request.venue == "china":
        explicit_source = (
            parameters.get("source")
            or parameters.get("providerSource")
            or parameters.get("provider")
            or parameters.get("parameters", {}).get("source")
        )
        if explicit_source is not None:
            source_context = resolve_source_context(
                {**clean, **parameters},
                source=str(explicit_source),
                allow_research_source=bool(parameters.get("allowResearchSource")),
                asset_class=request.asset_class,
                market="china",
                venue=request.venue,
            )
            clean = apply_source_context(clean, source_context)
        clean.update(ashare_trading_config(clean, parameters))
    clean["executionPolicy"] = _validate_execution_policy_parameters(clean)
    with db() as connection:
        connection.execute(
            """
            insert into paper_sessions
                (id, project_id, name, status, symbol, asset_class, venue, resolution, cash, equity,
                 parameters_json, created_at, updated_at, mode, legacy_read_only)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                parameters.get("projectId"),
                name,
                "created",
                request.symbol,
                request.asset_class,
                request.venue,
                request.resolution,
                cash,
                cash,
                json_dump(clean),
                now,
                now,
                "legacy_replay",
                0,
            ),
        )
    return get_session(session_id) or {}


def update_session_status(session_id: str, status: str) -> dict[str, Any]:
    if status not in {"created", "running", "paused", "stopped"}:
        raise ValueError("Paper session status must be created, running, paused, or stopped.")
    session = get_session(session_id)
    if not session:
        raise KeyError("Paper session not found.")
    if session.get("legacy_read_only"):
        raise ValueError("Legacy Paper Replay sessions are read-only.")
    if session.get("status") == "stopped" and status != "stopped":
        raise ValueError("Stopped LEAN Paper sessions are immutable.")
    now = utc_now()
    finished_at = now if status == "stopped" else None
    with db() as connection:
        connection.execute(
            "update paper_sessions set status = ?, updated_at = ?, finished_at = coalesce(?, finished_at) where id = ?",
            (status, now, finished_at, session_id),
        )
    return get_session(session_id) or {}


def _order_event_key(order: dict[str, Any]) -> str:
    payload = {
        "time": str(order.get("time") or order.get("lastFillTime") or ""),
        "symbol": str(order.get("symbol") or ""),
        "side": str(order.get("side") or "").upper(),
        "quantity": round(float(order.get("quantity") or 0), 8),
        "price": round(float(order.get("price") or order.get("fillPrice") or 0), 8),
        "status": str(order.get("status") or "").lower(),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _order_trade_date(order: dict[str, Any]) -> str:
    value = str(order.get("time") or order.get("lastFillTime") or "")
    return value[:10] if len(value) >= 10 else ""


def _orders_through(result: dict[str, Any] | None, end_date: str) -> list[dict[str, Any]]:
    orders = (result or {}).get("orders") or []
    return [dict(item) for item in orders if isinstance(item, dict) and _order_trade_date(item) <= end_date]


def _orders_fingerprint(orders: list[dict[str, Any]]) -> str:
    keys = sorted(_order_event_key(item) for item in orders)
    return hashlib.sha256("\n".join(keys).encode("utf-8")).hexdigest()


def create_walkforward_run(session_id: str, trade_date: str) -> dict[str, Any]:
    session = get_session(session_id)
    if not session:
        raise KeyError("Paper session not found.")
    if session.get("mode") != "lean_walkforward" or session.get("legacy_read_only"):
        raise ValueError("This session is not an active LEAN Paper session.")
    if session.get("status") == "stopped":
        raise ValueError("Stopped LEAN Paper sessions cannot run.")
    date_value = parse_date(trade_date).isoformat()
    if date_value < str(session.get("start_date") or ""):
        raise ValueError("tradeDate is before the Paper start date.")
    last_date = session.get("last_processed_date")
    expected = str(session.get("start_date")) if not last_date else _next_china_trade_date(str(last_date))
    if date_value != expected:
        raise ValueError(f"The next eligible Paper trade date is {expected}.")
    with db() as connection:
        existing = connection.execute(
            "select * from paper_walkforward_runs where session_id = ? and trade_date = ?",
            (session_id, date_value),
        ).fetchone()
    if existing:
        item = row_to_dict(existing) or {}
        if item.get("status") == "success":
            return item
        if item.get("status") in {"queued", "running"}:
            raise ValueError("This Paper trade date is already queued or running.")
    parameters = dict(session.get("parameters") or {})
    source_backtest_id = str(session.get("source_backtest_id") or parameters.get("sourceBacktestId") or "")
    source_run = get_backtest(source_backtest_id)
    if not source_run:
        raise ValueError("Source backtest is unavailable.")
    request_parameters = {
        key: value
        for key, value in parameters.items()
        if key not in {
            "ticker", "start", "end", "cash", "initialCash", "initial_cash",
            "strategySnapshotDir", "strategySnapshotMainFile",
            "strategySnapshotAlgorithmClass", "strategySnapshotLanguage",
        }
    }
    child = create_backtest_job(
        {
            "symbol": session["symbol"],
            "name": f"Paper {session['name']} through {date_value}",
            "assetClass": session["asset_class"],
            "market": session["venue"],
            "venue": session["venue"],
            "resolution": session["resolution"],
            "dataType": parameters.get("dataType", "trade"),
            "start": parameters["start"],
            "end": date_value,
            "cash": session["cash"],
            "dockerImage": source_run.get("docker_image"),
            "projectId": session["project_id"],
            "benchmarkSymbol": parameters.get("benchmarkSymbol"),
            "source": parameters.get("source"),
            "strategySnapshotSourceDir": parameters["strategySnapshotDir"],
            "strategySnapshotMainFile": parameters.get("strategySnapshotMainFile"),
            "strategySnapshotAlgorithmClass": parameters.get("strategySnapshotAlgorithmClass"),
            "strategySnapshotLanguage": parameters.get("strategySnapshotLanguage"),
            "parameters": request_parameters,
        }
    )
    mark_backtest_queued(child["id"])
    paper_run_id = str(uuid.uuid4())
    now = utc_now()
    with db() as connection:
        if existing:
            paper_run_id = str(existing["id"])
            connection.execute(
                """
                update paper_walkforward_runs
                set backtest_run_id = ?, task_id = ?, status = 'queued', failure_json = null,
                    reconciliation_json = null, started_at = null, finished_at = null
                where id = ?
                """,
                (child["id"], child["task_id"], paper_run_id),
            )
        else:
            connection.execute(
                """
                insert into paper_walkforward_runs
                    (id, session_id, trade_date, backtest_run_id, task_id, status, created_at)
                values (?, ?, ?, ?, ?, 'queued', ?)
                """,
                (paper_run_id, session_id, date_value, child["id"], child["task_id"], now),
            )
        connection.execute(
            "update paper_sessions set status = 'running', failure_json = null, updated_at = ? where id = ?",
            (now, session_id),
        )
    return get_walkforward_run(paper_run_id) or {}


def mark_walkforward_running(paper_run_id: str) -> None:
    with db() as connection:
        connection.execute(
            "update paper_walkforward_runs set status = 'running', started_at = ? where id = ?",
            (utc_now(), paper_run_id),
        )


def record_session_warning(session_id: str, code: str, message: str) -> None:
    failure = {"code": code, "message": message}
    with db() as connection:
        connection.execute(
            "update paper_sessions set failure_json = ?, updated_at = ? where id = ?",
            (json_dump(failure), utc_now(), session_id),
        )


def fail_walkforward_run(paper_run_id: str, error: str) -> dict[str, Any]:
    item = get_walkforward_run(paper_run_id)
    if not item:
        raise KeyError("Paper run not found.")
    failure = {"code": str(error).split(":", 1)[0], "message": str(error)}
    now = utc_now()
    with db() as connection:
        connection.execute(
            "update paper_walkforward_runs set status = 'failed', failure_json = ?, finished_at = ? where id = ?",
            (json_dump(failure), now, paper_run_id),
        )
        connection.execute(
            "update paper_sessions set status = 'paused', failure_json = ?, updated_at = ? where id = ?",
            (json_dump(failure), now, item["session_id"]),
        )
    return get_walkforward_run(paper_run_id) or {}


def _last_equity(result: dict[str, Any], fallback: float) -> float:
    curve = result.get("equity_curve") or []
    if curve:
        latest = curve[-1]
        if isinstance(latest, dict):
            for key in ("value", "y", "close"):
                if latest.get(key) is not None:
                    return float(latest[key])
        if isinstance(latest, (list, tuple)) and len(latest) >= 2:
            return float(latest[1])
    for key in ("End Equity", "EndEquity", "Final Equity"):
        raw = (result.get("statistics") or {}).get(key)
        if raw is not None:
            try:
                return float(str(raw).replace("$", "").replace(",", ""))
            except ValueError:
                pass
    return fallback


def finalize_walkforward_run(paper_run_id: str) -> dict[str, Any]:
    paper_run = get_walkforward_run(paper_run_id)
    if not paper_run:
        raise KeyError("Paper run not found.")
    session = get_session(str(paper_run["session_id"]))
    child = get_backtest(str(paper_run["backtest_run_id"]))
    if not session or not child:
        return fail_walkforward_run(paper_run_id, "paper_run_context_missing")
    if child.get("status") != "success" or (child.get("validation") or {}).get("passed") is not True:
        return fail_walkforward_run(
            paper_run_id,
            f"child_backtest_failed:{child.get('error_message') or child.get('error') or child.get('status')}",
        )
    result = get_result(child["id"])
    if not result:
        return fail_walkforward_run(paper_run_id, "child_backtest_result_missing")
    parameters = session.get("parameters") or {}
    baseline_date = str(session.get("last_processed_date") or (get_backtest(str(session["source_backtest_id"])) or {}).get("parameters", {}).get("end") or "")
    baseline_run_id = str(session.get("source_backtest_id"))
    if session.get("last_processed_date"):
        previous_runs = [
            item for item in list_walkforward_runs(session["id"])
            if item.get("status") == "success" and item.get("trade_date") == session.get("last_processed_date")
        ]
        if previous_runs:
            baseline_run_id = str(previous_runs[0]["backtest_run_id"])
    baseline_result = get_result(baseline_run_id)
    expected_orders = _orders_through(baseline_result, baseline_date)
    actual_prior_orders = _orders_through(result, baseline_date)
    expected_hash = _orders_fingerprint(expected_orders)
    actual_hash = _orders_fingerprint(actual_prior_orders)
    reconciliation = {
        "throughDate": baseline_date,
        "expectedOrderFingerprint": expected_hash,
        "actualOrderFingerprint": actual_hash,
        "passed": expected_hash == actual_hash,
    }
    if expected_hash != actual_hash:
        with db() as connection:
            connection.execute(
                "update paper_walkforward_runs set reconciliation_json = ? where id = ?",
                (json_dump(reconciliation), paper_run_id),
            )
        return fail_walkforward_run(paper_run_id, "history_reconciliation_failed")
    trade_date = str(paper_run["trade_date"])
    new_orders = [
        item for item in _orders_through(result, trade_date)
        if _order_trade_date(item) > baseline_date
    ]
    order_fingerprint = _orders_fingerprint(new_orders)
    equity = _last_equity(result, float(session["equity"]))
    holdings = [dict(item) for item in (result.get("holdings") or []) if isinstance(item, dict)]
    now = utc_now()
    with db() as connection:
        for order in new_orders:
            event_key = _order_event_key(order)
            event_id = str(uuid.uuid4())
            connection.execute(
                """
                insert into paper_lean_order_events
                    (id, session_id, paper_run_id, backtest_run_id, event_key, trade_date, event_json, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(session_id, event_key) do update set event_key = excluded.event_key
                """,
                (event_id, session["id"], paper_run_id, child["id"], event_key, _order_trade_date(order), json_dump(order), now),
            )
            side = str(order.get("side") or "").lower()
            quantity = abs(float(order.get("quantity") or 0))
            price = float(order.get("price") or order.get("fillPrice") or 0)
            connection.execute(
                """
                insert into paper_orders
                    (id, session_id, trade_date, symbol, side, quantity, order_price, fill_price,
                     fee, status, reason, created_at, filled_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
                on conflict(id) do update set id = excluded.id
                """,
                (
                    event_key,
                    session["id"],
                    _order_trade_date(order),
                    order.get("symbol") or session["symbol"],
                    side,
                    quantity,
                    price,
                    price,
                    order.get("status") or "filled",
                    order.get("tag"),
                    now,
                    str(order.get("time") or now),
                ),
            )
        connection.execute("delete from paper_positions where session_id = ?", (session["id"],))
        for holding in holdings:
            symbol = str(holding.get("symbol") or holding.get("Symbol") or session["symbol"])
            quantity = float(holding.get("quantity") or holding.get("Quantity") or 0)
            if quantity == 0:
                continue
            average = float(holding.get("averagePrice") or holding.get("AveragePrice") or holding.get("average_price") or 0)
            market_price = float(holding.get("price") or holding.get("Price") or holding.get("marketPrice") or 0)
            connection.execute(
                """
                insert into paper_positions
                    (session_id, symbol, quantity, average_price, market_price, market_value, updated_at)
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                (session["id"], symbol, quantity, average, market_price, quantity * market_price, now),
            )
        snapshot = {
            "source": "lean_walkforward",
            "paperRunId": paper_run_id,
            "backtestRunId": child["id"],
            "positions": holdings,
        }
        connection.execute(
            """
            insert into paper_portfolio_snapshots
                (id, session_id, trade_date, cash, market_value, equity, positions_json,
                 benchmark_symbol, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(session_id, trade_date) do update set
                cash = excluded.cash, market_value = excluded.market_value, equity = excluded.equity,
                positions_json = excluded.positions_json, benchmark_symbol = excluded.benchmark_symbol
            """,
            (
                str(uuid.uuid4()),
                session["id"],
                trade_date,
                max(0.0, equity - sum(float(item.get("marketValue") or item.get("market_value") or 0) for item in holdings)),
                sum(float(item.get("marketValue") or item.get("market_value") or 0) for item in holdings),
                equity,
                json_dump(holdings),
                parameters.get("benchmarkSymbol"),
                now,
            ),
        )
        report = {
            "schemaVersion": 2,
            "mode": "lean_walkforward",
            "sessionId": session["id"],
            "tradeDate": trade_date,
            "NAV": equity,
            "orders": new_orders,
            "positions": holdings,
            "statistics": result.get("statistics") or {},
            "summaryMetrics": result.get("summary_metrics") or {},
            "fingerprint": order_fingerprint,
            "reconciliation": reconciliation,
            "backtestRunId": child["id"],
            "qa": {"passed": True, "severity": "ok"},
        }
        connection.execute(
            """
            insert into paper_daily_reports
                (id, session_id, trade_date, report_json, signals_json, orders_json, trades_json,
                 rejects_json, positions_json, snapshot_json, benchmark_json, qa_json, created_at)
            values (?, ?, ?, ?, '[]', ?, ?, '[]', ?, ?, '{}', ?, ?)
            on conflict(session_id, trade_date) do update set
                report_json = excluded.report_json, orders_json = excluded.orders_json,
                trades_json = excluded.trades_json, positions_json = excluded.positions_json,
                snapshot_json = excluded.snapshot_json, qa_json = excluded.qa_json
            """,
            (
                str(uuid.uuid4()),
                session["id"],
                trade_date,
                json_dump(report),
                json_dump(new_orders),
                json_dump(new_orders),
                json_dump(holdings),
                json_dump(snapshot),
                json_dump(report["qa"]),
                now,
            ),
        )
        connection.execute(
            """
            update paper_walkforward_runs
            set status = 'success', order_fingerprint = ?, reconciliation_json = ?, finished_at = ?
            where id = ?
            """,
            (order_fingerprint, json_dump(reconciliation), now, paper_run_id),
        )
        connection.execute(
            """
            update paper_sessions
            set equity = ?, last_processed_date = ?, status = 'running', failure_json = null, updated_at = ?
            where id = ?
            """,
            (equity, trade_date, now, session["id"]),
        )
    return get_walkforward_run(paper_run_id) or {}


def _ashare_bar(symbol: str, trade_date: str, source: str | None = None) -> dict[str, Any] | None:
    source_clause = "and source = ?" if source else ""
    params: list[Any] = [symbol, trade_date]
    if source:
        params.append(source)
    with db() as connection:
        row = connection.execute(
            f"""
            select * from ashare_daily_bars
            where symbol = ? and trade_date = ? and adjust = 'raw'
              {source_clause}
            order by source desc
            limit 1
            """,
            params,
        ).fetchone()
    return row_to_dict(row)


def _market_bar(symbol: str, trade_date: str, *, asset_class: str = "equity", market: str = "china", source: str | None = None) -> dict[str, Any] | None:
    source_clause = "and source = ?" if source else ""
    params: list[Any] = [symbol, trade_date, asset_class, market]
    if source:
        params.append(source)
    with db() as connection:
        row = connection.execute(
            f"""
            select * from market_daily_bars
            where symbol = ? and trade_date = ? and asset_class = ? and market = ?
              and resolution = 'daily' and data_type = 'trade' and adjust = 'raw'
              {source_clause}
            order by source desc
            limit 1
            """,
            params,
        ).fetchone()
    return row_to_dict(row)


def _latest_ashare_bars(symbol: str, trade_date: str, limit: int, source: str | None = None) -> list[dict[str, Any]]:
    source_clause = "and source = ?" if source else ""
    params: list[Any] = [symbol, trade_date]
    if source:
        params.append(source)
    params.append(limit)
    with db() as connection:
        rows = connection.execute(
            f"""
            select * from ashare_daily_bars
            where symbol = ? and trade_date <= ? and adjust = 'raw'
              {source_clause}
            order by trade_date desc
            limit ?
            """,
            params,
        ).fetchall()
    return list(reversed(rows_to_dicts(rows)))


def create_signal(
    session_id: str,
    *,
    trade_date: str,
    side: str,
    symbol: str | None = None,
    target_percent: float | None = None,
    strength: float | None = None,
    reason: str | None = None,
    source: str = "manual",
) -> dict[str, Any]:
    session = get_session(session_id)
    if not session:
        raise KeyError("Paper session not found.")
    if session.get("legacy_read_only"):
        raise ValueError("Legacy Paper Replay sessions are read-only.")
    if session.get("mode") == "lean_walkforward":
        raise ValueError("LEAN Paper orders must originate from the frozen project strategy.")
    signal_symbol = _normalize_session_symbol(session, symbol or session["symbol"])
    signal_id = str(uuid.uuid4())
    now = utc_now()
    with db() as connection:
        connection.execute(
            """
            insert into paper_signals
                (id, session_id, trade_date, symbol, side, target_percent, strength, reason, status, source, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal_id,
                session_id,
                parse_date(trade_date).isoformat(),
                signal_symbol,
                _side(side),
                target_percent,
                strength,
                reason,
                "created",
                source,
                now,
            ),
        )
    return _get_signal(signal_id) or {}


def _get_signal(signal_id: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute("select * from paper_signals where id = ?", (signal_id,)).fetchone()
    return row_to_dict(row)


def generate_daily_signal(session_id: str, trade_date: str) -> dict[str, Any]:
    session = get_session(session_id)
    if not session:
        raise KeyError("Paper session not found.")
    parameters = session.get("parameters") or {}
    symbol = session["symbol"]
    return generate_daily_signal_for_symbol(session_id, symbol, trade_date)


def generate_daily_signal_for_symbol(session_id: str, symbol: str, trade_date: str) -> dict[str, Any]:
    session = get_session(session_id)
    if not session:
        raise KeyError("Paper session not found.")
    parameters = session.get("parameters") or {}
    symbol = _normalize_session_symbol(session, symbol)
    date_value = parse_date(trade_date).isoformat()
    fast = int(parameters.get("fast") or parameters.get("parameters", {}).get("fast") or 5)
    slow = int(parameters.get("slow") or parameters.get("parameters", {}).get("slow") or 20)
    if fast >= slow:
        slow = fast + 1
    bars = _latest_ashare_bars(symbol, date_value, slow, source=parameters.get("source"))
    if len(bars) < slow:
        return create_signal(
            session_id,
            trade_date=date_value,
            side="hold",
            symbol=symbol,
            target_percent=None,
            strength=0,
            reason=f"insufficient_history:{len(bars)}/{slow}",
            source="ema_cross",
        )
    fast_average = sum(float(row["close"]) for row in bars[-fast:]) / fast
    slow_average = sum(float(row["close"]) for row in bars[-slow:]) / slow
    position = _position(session_id, symbol)
    holding = bool(position and float(position.get("quantity") or 0) > 0)
    target_percent = _parameter_float(parameters, "signalTargetPercent", "targetPercent", "autoTargetPercent") or 1.0
    if fast_average > slow_average and not holding:
        return create_signal(session_id, trade_date=date_value, side="buy", symbol=symbol, target_percent=target_percent, strength=fast_average - slow_average, reason="fast_ma_above_slow_ma", source="ema_cross")
    if fast_average < slow_average and holding:
        return create_signal(session_id, trade_date=date_value, side="sell", symbol=symbol, target_percent=0.0, strength=slow_average - fast_average, reason="fast_ma_below_slow_ma", source="ema_cross")
    return create_signal(session_id, trade_date=date_value, side="hold", symbol=symbol, target_percent=None, strength=abs(fast_average - slow_average), reason="no_rebalance", source="ema_cross")


def _position(session_id: str, symbol: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute(
            "select * from paper_positions where session_id = ? and symbol = ?",
            (session_id, symbol),
        ).fetchone()
    return row_to_dict(row)


def _open_signals(session_id: str, trade_date: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            """
            select * from paper_signals
            where session_id = ? and trade_date = ? and status = 'created'
            order by created_at asc
            """,
            (session_id, trade_date),
        ).fetchall()
    return rows_to_dicts(rows)


def _signals_for_date(session_id: str, trade_date: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            """
            select * from paper_signals
            where session_id = ? and trade_date = ?
            order by created_at asc
            """,
            (session_id, trade_date),
        ).fetchall()
    return rows_to_dicts(rows)


def _signals_for_date_symbol(session_id: str, trade_date: str, symbol: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            """
            select * from paper_signals
            where session_id = ? and trade_date = ? and symbol = ?
            order by created_at asc
            """,
            (session_id, trade_date, symbol),
        ).fetchall()
    return rows_to_dicts(rows)


def _session_parameters(session: dict[str, Any]) -> dict[str, Any]:
    return session.get("parameters") or {}


def _session_symbols(session: dict[str, Any]) -> list[str]:
    parameters = _session_parameters(session)
    symbols = parameters.get("symbols") or parameters.get("paperSymbols") or []
    if isinstance(symbols, str):
        symbols = [item.strip() for item in symbols.split(",") if item.strip()]
    if not symbols:
        symbols = [session["symbol"]]
    result = []
    for symbol in symbols:
        normalized = _normalize_session_symbol(session, str(symbol))
        if normalized not in result:
            result.append(normalized)
    return result


def _normalize_session_symbol(session: dict[str, Any], symbol: str) -> str:
    if session.get("asset_class") == "equity" and session.get("venue") == "china":
        return normalize_symbol(symbol, "china")
    return str(symbol).upper().strip()


def _parameter_list(parameters: dict[str, Any], *keys: str) -> set[str]:
    for key in keys:
        if key not in parameters:
            continue
        value = parameters.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            return {item.strip().upper() for item in value.split(",") if item.strip()}
        if isinstance(value, (list, tuple, set)):
            return {str(item).strip().upper() for item in value if str(item).strip()}
    return set()


def _parameter_float(parameters: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key in parameters and parameters.get(key) not in (None, ""):
            return float(parameters[key])
    return None


def _parameter_int(parameters: dict[str, Any], *keys: str) -> int | None:
    value = _parameter_float(parameters, *keys)
    return int(value) if value is not None else None


def _parameter_bool(parameters: dict[str, Any], key: str, default: bool = False) -> bool:
    value = parameters.get(key)
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _normalize_execution_policy(policy: str | None) -> str:
    value = str(policy or "next_open").strip().lower()
    aliases = {
        "nextopen": "next_open",
        "next-close": "next_close",
        "nextclose": "next_close",
        "next-vwap": "next_vwap",
        "nextvwap": "next_vwap",
        "sameclose": "same_close",
        "same-day-close": "same_close",
    }
    value = aliases.get(value, value)
    if value not in {"next_open", "next_close", "next_vwap", "same_close"}:
        raise ValueError("executionPolicy must be next_open, next_close, next_vwap, or same_close.")
    return value


def _validate_execution_policy_parameters(parameters: dict[str, Any]) -> str:
    policy = _normalize_execution_policy(parameters.get("executionPolicy") or parameters.get("execution_policy"))
    if policy == "same_close" and not _parameter_bool(parameters, "allowSameDayClose", False):
        raise ValueError("same_close executionPolicy is disabled unless allowSameDayClose is true.")
    return policy


def _execution_policy(session: dict[str, Any]) -> str:
    parameters = _session_parameters(session)
    return _validate_execution_policy_parameters(parameters)


def _next_trade_date(symbol: str, trade_date: str) -> str | None:
    date_value = parse_date(trade_date).isoformat()
    with db() as connection:
        row = connection.execute(
            """
            select trade_date
            from trade_calendar
            where market = 'china' and is_open = 1 and trade_date > ?
            order by trade_date asc
            limit 1
            """,
            (date_value,),
        ).fetchone()
        if row:
            return row["trade_date"]
        row = connection.execute(
            """
            select distinct trade_date
            from ashare_daily_bars
            where symbol = ? and trade_date > ?
            order by trade_date asc
            limit 1
            """,
            (symbol, date_value),
        ).fetchone()
    return row["trade_date"] if row else None


def _signal_execution_date(session: dict[str, Any], signal: dict[str, Any], policy: str) -> str | None:
    signal_date = parse_date(signal["trade_date"]).isoformat()
    if policy == "same_close":
        return signal_date
    return _next_trade_date(signal["symbol"], signal_date)


def _open_signals_due(session: dict[str, Any], execution_date: str, policy: str) -> list[dict[str, Any]]:
    date_value = parse_date(execution_date).isoformat()
    with db() as connection:
        rows = connection.execute(
            """
            select * from paper_signals
            where session_id = ? and trade_date <= ? and status = 'created'
            order by trade_date asc, created_at asc
            """,
            (session["id"], date_value),
        ).fetchall()
    due = []
    for signal in rows_to_dicts(rows):
        if _signal_execution_date(session, signal, policy) == date_value:
            due.append(signal)
    return due


def _execution_bar(session: dict[str, Any], symbol: str, execution_date: str) -> dict[str, Any] | None:
    return _ashare_bar(symbol, execution_date, source=(_session_parameters(session).get("source")))


def _execution_price(bar: dict[str, Any], policy: str) -> float:
    if policy == "next_open":
        return float(bar["open"])
    if policy == "next_vwap":
        amount = bar.get("amount")
        volume = float(bar.get("volume") or 0)
        if amount not in (None, "") and volume > 0:
            value = float(amount)
            if value > 0:
                return value / volume
        return float(bar["close"])
    return float(bar["close"])


def _float_parameter(parameters: dict[str, Any], key: str, default: float) -> float:
    value = parameters.get(key)
    if value in (None, ""):
        return default
    return float(value)


def _fee(quantity: float, price: float, side: str, session: dict[str, Any]) -> float:
    parameters = session.get("parameters") or {}
    value = abs(quantity * price)
    commission = max(value * _float_parameter(parameters, "commissionRate", 0.0001), _float_parameter(parameters, "minCommission", 5.0)) if value else 0
    stamp_tax = value * _float_parameter(parameters, "stampTaxSell", 0.0005) if side == "sell" else 0
    transfer = value * _float_parameter(parameters, "transferFeeRate", 0.00001)
    return commission + stamp_tax + transfer


def _round_lot(quantity: float, lot_size: int = 100) -> int:
    if quantity == 0:
        return 0
    sign = 1 if quantity > 0 else -1
    return sign * (abs(int(quantity)) // lot_size) * lot_size


def _status_for(symbol: str, trade_date: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute(
            "select * from ashare_trade_status where symbol = ? and trade_date = ?",
            (symbol, trade_date),
        ).fetchone()
    status = row_to_dict(row)
    if not status:
        return None
    for field in ("is_suspended", "is_limit_up", "is_limit_down", "can_buy", "can_sell", "is_st"):
        if field in status:
            status[field] = bool(status[field])
    return status


def _portfolio_constraint_rejection(
    session: dict[str, Any],
    signal: dict[str, Any],
    side: str,
    execution_date: str,
    current_quantity: float,
) -> str | None:
    if side != "buy":
        return None
    parameters = _session_parameters(session)
    symbol = str(signal["symbol"]).upper()
    if symbol in _parameter_list(parameters, "blacklist", "blacklistSymbols", "blockedSymbols"):
        return "blacklisted"
    if symbol in _parameter_list(parameters, "observeOnlySymbols", "observe_only_symbols", "observeOnly"):
        return "observe_only"
    watchlist = _parameter_list(parameters, "watchlist", "watchlistSymbols", "observableSymbols")
    if watchlist and symbol not in watchlist:
        return "not_in_watchlist"
    if not _parameter_bool(parameters, "allowStBuy", False):
        status = _status_for(symbol, execution_date)
        if status and status.get("is_st"):
            return "st_blocked"
    max_positions = _parameter_int(parameters, "maxPositions", "max_positions", "maxHoldings")
    if max_positions is not None and current_quantity <= 0:
        current_positions = [position for position in list_positions(session["id"]) if float(position.get("quantity") or 0) > 0]
        if len(current_positions) >= max_positions:
            return "max_positions"
    return None


def _target_percent_rejection(session: dict[str, Any], signal: dict[str, Any]) -> str | None:
    cap = _parameter_float(_session_parameters(session), "maxPositionWeight", "max_position_weight", "singleStockMaxWeight")
    requested = float(signal.get("target_percent") or 1.0)
    if cap is not None and requested - cap > 1e-12:
        return "max_position_weight"
    return None


def _target_percent(session: dict[str, Any], signal: dict[str, Any]) -> float:
    target = float(signal.get("target_percent") or 1.0)
    cap = _parameter_float(_session_parameters(session), "maxPositionWeight", "max_position_weight", "singleStockMaxWeight")
    if cap is not None:
        target = min(target, max(0.0, cap))
    return max(0.0, target)


def _update_signal(signal_id: str, status: str) -> None:
    with db() as connection:
        connection.execute("update paper_signals set status = ? where id = ?", (status, signal_id))


def _record_order(
    session_id: str,
    signal: dict[str, Any],
    side: str,
    quantity: float,
    trade_date: str,
    order_price: float | None,
    fill_price: float | None,
    fee: float,
    status: str,
    reason: str | None = None,
) -> dict[str, Any]:
    order_id = str(uuid.uuid4())
    now = utc_now()
    with db() as connection:
        connection.execute(
            """
            insert into paper_orders
                (id, session_id, signal_id, trade_date, symbol, side, quantity, order_price,
                 fill_price, fee, status, reason, created_at, filled_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_id,
                session_id,
                signal.get("id"),
                trade_date,
                signal["symbol"],
                side,
                quantity,
                order_price,
                fill_price,
                fee,
                status,
                reason,
                now,
                now if status == "filled" else None,
            ),
        )
    with db() as connection:
        row = connection.execute("select * from paper_orders where id = ?", (order_id,)).fetchone()
    return row_to_dict(row) or {}


def _apply_fill(session: dict[str, Any], symbol: str, side: str, quantity: float, price: float, fee: float, trade_date: str) -> None:
    position = _position(session["id"], symbol)
    current_quantity = float((position or {}).get("quantity") or 0)
    average_price = float((position or {}).get("average_price") or 0)
    cash = float(session["cash"])
    signed = quantity if side == "buy" else -quantity
    new_quantity = current_quantity + signed
    if side == "buy":
        cost = quantity * price + fee
        cash -= cost
        average_price = ((current_quantity * average_price) + (quantity * price)) / new_quantity if new_quantity else 0
        last_buy_date = trade_date
    else:
        cash += quantity * price - fee
        last_buy_date = (position or {}).get("last_buy_date")
        if new_quantity <= 0:
            average_price = 0
    now = utc_now()
    with db() as connection:
        if new_quantity <= 0:
            connection.execute("delete from paper_positions where session_id = ? and symbol = ?", (session["id"], symbol))
        else:
            connection.execute(
                """
                insert into paper_positions
                    (session_id, symbol, quantity, average_price, market_price, market_value, last_buy_date, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(session_id, symbol) do update set
                    quantity = excluded.quantity,
                    average_price = excluded.average_price,
                    market_price = excluded.market_price,
                    market_value = excluded.market_value,
                    last_buy_date = excluded.last_buy_date,
                    updated_at = excluded.updated_at
                """,
                (session["id"], symbol, new_quantity, average_price, price, new_quantity * price, last_buy_date, now),
            )
        connection.execute("update paper_sessions set cash = ?, updated_at = ? where id = ?", (cash, now, session["id"]))


def match_daily_orders(session_id: str, trade_date: str, auto_signal: bool = True) -> dict[str, Any]:
    session = get_session(session_id)
    if not session:
        raise KeyError("Paper session not found.")
    date_value = parse_date(trade_date).isoformat()
    policy = _execution_policy(session)
    # Daily Paper Replay executes previously generated signals first. New auto
    # signals are today's close decisions and are eligible from the next session.
    signals = _open_signals_due(session, date_value, policy)
    orders = []
    for signal in signals:
        side = signal["side"]
        if side == "hold":
            _update_signal(signal["id"], "processed")
            continue
        gate = quality_gate(signal["symbol"], date_value)
        if not gate["passed"]:
            report_id = gate["blockingReports"][0].get("id") if gate["blockingReports"] else None
            reason = f"qa_failed:{report_id}" if report_id else "qa_failed"
            orders.append(_record_order(session_id, signal, side, 0, date_value, None, None, 0, "rejected", reason))
            _update_signal(signal["id"], "rejected")
            continue
        bar = _execution_bar(session, signal["symbol"], date_value)
        if not bar:
            orders.append(_record_order(session_id, signal, side, 0, date_value, None, None, 0, "rejected", "bar_missing"))
            _update_signal(signal["id"], "rejected")
            continue
        can_trade, reason = is_tradeable(signal["symbol"], date_value, side)
        if not can_trade:
            orders.append(_record_order(session_id, signal, side, 0, date_value, float(bar["close"]), None, 0, "rejected", reason))
            _update_signal(signal["id"], "rejected")
            continue
        session = get_session(session_id) or session
        position = _position(session_id, signal["symbol"])
        current_quantity = float((position or {}).get("quantity") or 0)
        price = _execution_price(bar, policy)
        lot_size = int((session.get("parameters") or {}).get("lotSize") or 100)
        constraint_reason = _portfolio_constraint_rejection(session, signal, side, date_value, current_quantity)
        if constraint_reason:
            orders.append(_record_order(session_id, signal, side, 0, date_value, price, None, 0, "rejected", constraint_reason))
            _update_signal(signal["id"], "rejected")
            continue
        target_rejection = _target_percent_rejection(session, signal) if side == "buy" else None
        if target_rejection:
            orders.append(_record_order(session_id, signal, side, 0, date_value, price, None, 0, "rejected", target_rejection))
            _update_signal(signal["id"], "rejected")
            continue
        if side == "buy":
            target = _target_percent(session, signal)
            desired = _round_lot((float(session["equity"]) * target) / price, lot_size)
            quantity = max(0, desired - current_quantity)
            quantity = _round_lot(quantity, lot_size)
            fee = _fee(quantity, price, side, session)
            min_cash = _parameter_float(_session_parameters(session), "minCash", "min_cash", "cashFloor") or 0.0
            available_cash = max(0.0, float(session["cash"]) - min_cash)
            max_cash_quantity = _round_lot((available_cash - fee) / price, lot_size)
            quantity = max(0, min(quantity, max_cash_quantity))
            if quantity <= 0:
                reason = "cash_floor" if available_cash <= 0 else "insufficient_cash"
                orders.append(_record_order(session_id, signal, side, 0, date_value, price, None, 0, "rejected", reason))
                _update_signal(signal["id"], "rejected")
                continue
        else:
            if (position or {}).get("last_buy_date") == date_value:
                orders.append(_record_order(session_id, signal, side, 0, date_value, price, None, 0, "rejected", "t_plus_1"))
                _update_signal(signal["id"], "rejected")
                continue
            quantity = _round_lot(current_quantity, lot_size)
            fee = _fee(quantity, price, side, session)
        if quantity <= 0:
            reason = "insufficient_position" if side == "sell" else "lot_size"
            orders.append(_record_order(session_id, signal, side, 0, date_value, price, None, 0, "rejected", reason))
            _update_signal(signal["id"], "rejected")
            continue
        fee = _fee(quantity, price, side, session)
        _apply_fill(session, signal["symbol"], side, quantity, price, fee, date_value)
        orders.append(_record_order(session_id, signal, side, quantity, date_value, price, price, fee, "filled"))
        _update_signal(signal["id"], "filled")
    if auto_signal:
        for symbol in _session_symbols(session):
            if not _signals_for_date_symbol(session_id, date_value, symbol):
                generate_daily_signal_for_symbol(session_id, symbol, date_value)
    snapshot = create_snapshot(session_id, date_value)
    report = create_daily_report(session_id, date_value)
    return {"date": date_value, "executionPolicy": policy, "signals": signals, "orders": orders, "snapshot": snapshot, "report": report}


def _replay_dates(session: dict[str, Any], start_date: str, end_date: str) -> list[str]:
    start = parse_date(start_date).isoformat()
    end = parse_date(end_date).isoformat()
    symbols = _session_symbols(session)
    if session.get("asset_class") == "equity" and session.get("venue") == "china":
        with db() as connection:
            calendar_rows = connection.execute(
                """
                select trade_date
                from trade_calendar
                where market = 'china' and is_open = 1 and trade_date between ? and ?
                order by trade_date asc
                """,
                (start, end),
            ).fetchall()
        dates = [row["trade_date"] for row in calendar_rows]
        if dates:
            return dates
        with db() as connection:
            rows = connection.execute(
                """
                select distinct trade_date
                from ashare_daily_bars
                where symbol in ({",".join("?" for _ in symbols)}) and trade_date between ? and ?
                order by trade_date asc
                """,
                (*symbols, start, end),
            ).fetchall()
        return [row["trade_date"] for row in rows]
    return []


def run_replay(session_id: str, start_date: str, end_date: str, auto_signal: bool = True) -> dict[str, Any]:
    session = get_session(session_id)
    if not session:
        raise KeyError("Paper session not found.")
    if session.get("mode") == "lean_walkforward":
        raise ValueError("LEAN Paper replay must be queued through the walk-forward runner.")
    dates = _replay_dates(session, start_date, end_date)
    update_session_status(session_id, "running")
    days = []
    try:
        for trade_date in dates:
            days.append(match_daily_orders(session_id, trade_date, auto_signal=auto_signal))
    finally:
        update_session_status(session_id, "paused")
    return {
        "sessionId": session_id,
        "startDate": parse_date(start_date).isoformat(),
        "endDate": parse_date(end_date).isoformat(),
        "tradingDays": len(dates),
        "days": days,
        "finalSession": get_session(session_id),
        "positions": list_positions(session_id),
        "snapshots": list_snapshots(session_id),
        "reports": list_daily_reports(session_id),
    }


def _orders_for_date(session_id: str, trade_date: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            """
            select * from paper_orders
            where session_id = ? and trade_date = ?
            order by created_at asc
            """,
            (session_id, trade_date),
        ).fetchall()
    return rows_to_dicts(rows)


def _latest_snapshot(session_id: str, trade_date: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute(
            "select * from paper_portfolio_snapshots where session_id = ? and trade_date = ?",
            (session_id, trade_date),
        ).fetchone()
    return row_to_dict(row)


def _previous_snapshot(session_id: str, trade_date: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute(
            """
            select * from paper_portfolio_snapshots
            where session_id = ? and trade_date < ?
            order by trade_date desc
            limit 1
            """,
            (session_id, trade_date),
        ).fetchone()
    return row_to_dict(row)


def _position_weights(positions: list[dict[str, Any]], equity: float) -> list[dict[str, Any]]:
    result = []
    for position in positions:
        market_value = float(position.get("market_value") or 0)
        result.append(
            {
                "symbol": position.get("symbol"),
                "marketValue": market_value,
                "weight": market_value / equity if equity else 0.0,
            }
        )
    return result


def _data_source_status(session: dict[str, Any], trade_date: str, benchmark_symbol: str | None) -> dict[str, Any]:
    source = _session_parameters(session).get("source")
    symbols = []
    for symbol in _session_symbols(session):
        bar = _market_bar(symbol, trade_date, asset_class=session.get("asset_class") or "equity", market=session.get("venue") or "china", source=source) or _ashare_bar(symbol, trade_date, source=source)
        symbols.append({"symbol": symbol, "available": bar is not None, "source": (bar or {}).get("source")})
    benchmark_bar = None
    if benchmark_symbol:
        benchmark_bar = _market_bar(benchmark_symbol, trade_date, asset_class="equity", market="china", source=source) or _ashare_bar(benchmark_symbol, trade_date, source=source)
    return {
        "symbols": symbols,
        "benchmark": {
            "symbol": benchmark_symbol,
            "available": benchmark_bar is not None if benchmark_symbol else False,
            "source": (benchmark_bar or {}).get("source"),
        },
    }


def _paper_report_fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def create_daily_report(session_id: str, trade_date: str) -> dict[str, Any]:
    session = get_session(session_id)
    if not session:
        raise KeyError("Paper session not found.")
    date_value = parse_date(trade_date).isoformat()
    policy = _execution_policy(session)
    signals = _signals_for_date(session_id, date_value)
    execution_signals = _open_signals_due(session, date_value, policy)
    orders = _orders_for_date(session_id, date_value)
    trades = [order for order in orders if order.get("status") == "filled"]
    rejects = [order for order in orders if order.get("status") == "rejected"]
    previous_snapshot = _previous_snapshot(session_id, date_value)
    snapshot = _latest_snapshot(session_id, date_value) or create_snapshot(session_id, date_value)
    positions = list_positions(session_id)
    initial_cash = float((_session_parameters(session).get("cash") or 0) or 0)
    if initial_cash <= 0:
        initial_cash = float(snapshot.get("equity") or session.get("equity") or session.get("cash") or 0)
    equity = float(snapshot.get("equity") or 0)
    cash = float(snapshot.get("cash") or session.get("cash") or 0)
    previous_equity = float((previous_snapshot or {}).get("equity") or 0)
    daily_return = equity / previous_equity - 1.0 if previous_equity else 0.0
    cumulative_return = equity / initial_cash - 1.0 if initial_cash else None
    benchmark = {
        "symbol": snapshot.get("benchmark_symbol"),
        "close": snapshot.get("benchmark_close"),
        "return": snapshot.get("benchmark_return"),
    }
    previous_benchmark_close = float((previous_snapshot or {}).get("benchmark_close") or 0)
    benchmark_close = float(snapshot.get("benchmark_close") or 0)
    benchmark_daily_return = benchmark_close / previous_benchmark_close - 1.0 if previous_benchmark_close and benchmark_close else 0.0
    benchmark["dailyReturn"] = benchmark_daily_return
    excess_return = (
        cumulative_return - float(snapshot.get("benchmark_return"))
        if cumulative_return is not None and snapshot.get("benchmark_return") is not None
        else None
    )
    position_weights = _position_weights(positions, equity)
    qa_items = [quality_gate(symbol, date_value) for symbol in _session_symbols(session)]
    qa = {
        "passed": all(item["passed"] for item in qa_items),
        "severity": "critical" if any(item["severity"] == "critical" for item in qa_items) else "ok",
        "items": qa_items,
    }
    data_source_status = _data_source_status(session, date_value, snapshot.get("benchmark_symbol"))
    coverage_summary = ashare_coverage(
        symbols=_session_symbols(session),
        benchmark=snapshot.get("benchmark_symbol") or _session_parameters(session).get("benchmarkSymbol") or "000300",
        start_date=date_value,
        end_date=date_value,
        source=_session_parameters(session).get("source"),
    )
    warnings = []
    if benchmark.get("symbol") and not benchmark.get("close"):
        warnings.append("benchmark_missing")
    warnings.extend(f"data_missing:{item['symbol']}" for item in data_source_status["symbols"] if not item["available"])
    if not data_source_status["benchmark"]["available"] and benchmark.get("symbol"):
        warnings.append(f"benchmark_source_missing:{benchmark['symbol']}")
    if qa["severity"] != "ok":
        warnings.append(f"qa_{qa['severity']}")
    if coverage_summary["severity"] == "warning":
        warnings.extend(coverage_summary.get("warnings") or ["coverage_warning"])
    fingerprint = _paper_report_fingerprint(
        {
            "session_id": session_id,
            "trade_date": date_value,
            "parameters": session.get("parameters") or {},
            "orders": [
                {
                    "id": order.get("id"),
                    "symbol": order.get("symbol"),
                    "side": order.get("side"),
                    "quantity": order.get("quantity"),
                    "status": order.get("status"),
                    "reason": order.get("reason"),
                    "fill_price": order.get("fill_price"),
                }
                for order in orders
            ],
            "snapshot": {
                "cash": cash,
                "equity": equity,
                "benchmark_symbol": benchmark.get("symbol"),
                "benchmark_close": benchmark.get("close"),
            },
            "qa": qa,
        }
    )
    report = {
        "schemaVersion": 1,
        "sessionId": session_id,
        "tradeDate": date_value,
        "strategy": _session_parameters(session).get("strategy") or _session_parameters(session).get("strategyKey") or "ema_cross",
        "executionPolicy": policy,
        "initialCash": initial_cash,
        "cash": cash,
        "NAV": equity,
        "nav": equity,
        "dailyReturn": daily_return,
        "cumulativeReturn": cumulative_return,
        "excessReturn": excess_return,
        "signals": signals,
        "pendingSignals": execution_signals,
        "executionSignals": execution_signals,
        "orders": orders,
        "trades": trades,
        "rejects": rejects,
        "rejectionReasons": [order.get("reason") for order in rejects if order.get("reason")],
        "positions": positions,
        "positionWeights": position_weights,
        "snapshot": snapshot,
        "benchmark": benchmark,
        "qa": qa,
        "dataSourceStatus": data_source_status,
        "coverageSummary": coverage_summary,
        "warnings": warnings,
        "fingerprint": fingerprint,
        "generatedAt": utc_now(),
    }
    report_id = str(uuid.uuid4())
    now = report["generatedAt"]
    with db() as connection:
        connection.execute(
            """
            insert into paper_daily_reports
                (id, session_id, trade_date, report_json, signals_json, orders_json,
                 trades_json, rejects_json, positions_json, snapshot_json, benchmark_json, qa_json, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(session_id, trade_date) do update set
                report_json = excluded.report_json,
                signals_json = excluded.signals_json,
                orders_json = excluded.orders_json,
                trades_json = excluded.trades_json,
                rejects_json = excluded.rejects_json,
                positions_json = excluded.positions_json,
                snapshot_json = excluded.snapshot_json,
                benchmark_json = excluded.benchmark_json,
                qa_json = excluded.qa_json,
                created_at = excluded.created_at
            """,
            (
                report_id,
                session_id,
                date_value,
                json_dump(report),
                json_dump(signals),
                json_dump(orders),
                json_dump(trades),
                json_dump(rejects),
                json_dump(positions),
                json_dump(snapshot),
                json_dump(benchmark),
                json_dump(qa),
                now,
            ),
        )
        row = connection.execute(
            "select * from paper_daily_reports where session_id = ? and trade_date = ?",
            (session_id, date_value),
        ).fetchone()
    return row_to_dict(row) or report


def create_snapshot(session_id: str, trade_date: str) -> dict[str, Any]:
    session = get_session(session_id)
    if not session:
        raise KeyError("Paper session not found.")
    date_value = parse_date(trade_date).isoformat()
    positions = list_positions(session_id)
    source = _session_parameters(session).get("source")
    market_value = 0.0
    for position in positions:
        bar = _ashare_bar(position["symbol"], date_value, source=source)
        price = float((bar or {}).get("close") or position.get("market_price") or position.get("average_price") or 0)
        value = float(position["quantity"]) * price
        market_value += value
        with db() as connection:
            connection.execute(
                "update paper_positions set market_price = ?, market_value = ?, updated_at = ? where session_id = ? and symbol = ?",
                (price, value, utc_now(), session_id, position["symbol"]),
            )
    cash = float(session["cash"])
    equity = cash + market_value
    benchmark_symbol = str(_session_parameters(session).get("benchmarkSymbol") or "").upper() or None
    benchmark_close = None
    benchmark_return = None
    if benchmark_symbol:
        benchmark_bar = _market_bar(benchmark_symbol, date_value, asset_class="equity", market="china", source=source) or _ashare_bar(benchmark_symbol, date_value, source=source)
        if benchmark_bar:
            benchmark_close = float(benchmark_bar["close"])
            with db() as connection:
                first_snapshot = connection.execute(
                    """
                    select benchmark_close from paper_portfolio_snapshots
                    where session_id = ? and benchmark_symbol = ? and benchmark_close is not null
                    order by trade_date asc
                    limit 1
                    """,
                        (session_id, benchmark_symbol),
                    ).fetchone()
            first_snapshot_item = row_to_dict(first_snapshot)
            base = (
                float(first_snapshot_item["benchmark_close"])
                if first_snapshot_item and first_snapshot_item.get("benchmark_close")
                else benchmark_close
            )
            benchmark_return = benchmark_close / base - 1.0 if base else None
    snapshot_id = str(uuid.uuid4())
    now = utc_now()
    with db() as connection:
        connection.execute(
            """
            insert into paper_portfolio_snapshots
                (id, session_id, trade_date, cash, market_value, equity, positions_json,
                 benchmark_symbol, benchmark_close, benchmark_return, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(session_id, trade_date) do update set
                cash = excluded.cash,
                market_value = excluded.market_value,
                equity = excluded.equity,
                positions_json = excluded.positions_json,
                benchmark_symbol = excluded.benchmark_symbol,
                benchmark_close = excluded.benchmark_close,
                benchmark_return = excluded.benchmark_return,
                created_at = excluded.created_at
            """,
            (
                snapshot_id,
                session_id,
                date_value,
                cash,
                market_value,
                equity,
                json_dump(list_positions(session_id)),
                benchmark_symbol,
                benchmark_close,
                benchmark_return,
                now,
            ),
        )
        connection.execute("update paper_sessions set equity = ?, updated_at = ? where id = ?", (equity, now, session_id))
        row = connection.execute(
            "select * from paper_portfolio_snapshots where session_id = ? and trade_date = ?",
            (session_id, date_value),
        ).fetchone()
    return row_to_dict(row) or {}
