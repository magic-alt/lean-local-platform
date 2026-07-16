from __future__ import annotations

import hashlib
import json
import math
import uuid
from dataclasses import dataclass
from statistics import mean
from typing import Any

from ..db import db, json_dump, row_to_dict, utc_now


PROFILE_VERSION = "admission-v1"
STAGE_SEQUENCE = ("research", "baseline_registered", "admission_passed", "paper_validated")
REQUIRED_REGIMES = {"bull", "bear", "range", "high-vol"}

SEED_SAMPLE_SET = [
    {"id": "cn_single_bear_q1_2024", "symbols": ["600519"], "start": "2024-01-02", "end": "2024-02-29", "regime": "bear"},
    {"id": "cn_single_range_mid_2024", "symbols": ["600519"], "start": "2024-03-01", "end": "2024-08-30", "regime": "range"},
    {"id": "cn_single_high_vol_q4_2024", "symbols": ["600519"], "start": "2024-09-02", "end": "2024-10-31", "regime": "high-vol"},
    {"id": "cn_single_bull_q4_2024", "symbols": ["601318"], "start": "2024-11-01", "end": "2024-12-31", "regime": "bull"},
    {"id": "cn_single_quality_2024", "symbols": ["600519"], "start": "2024-01-02", "end": "2024-12-31", "regime": "mixed"},
    {"id": "cn_single_financial_2024_2025", "symbols": ["600036"], "start": "2024-01-02", "end": "2025-10-14", "regime": "mixed"},
    {"id": "cn_multi_bear_q1_2024", "symbols": ["600519", "601318", "600036"], "start": "2024-01-02", "end": "2024-02-29", "regime": "bear"},
    {"id": "cn_multi_range_mid_2024", "symbols": ["600519", "601318", "600036"], "start": "2024-03-01", "end": "2024-08-30", "regime": "range"},
    {"id": "cn_multi_high_vol_q4_2024", "symbols": ["600519", "601318", "600036"], "start": "2024-09-02", "end": "2024-10-31", "regime": "high-vol"},
    {"id": "cn_multi_bull_q4_2024", "symbols": ["600519", "601318", "600036"], "start": "2024-11-01", "end": "2024-12-31", "regime": "bull"},
    {"id": "cn_multi_leaders_2024_2025", "symbols": ["600519", "601318", "600036"], "start": "2024-01-02", "end": "2025-10-14", "regime": "mixed"},
]


@dataclass(frozen=True)
class AdmissionProfile:
    min_sharpe: float
    max_mdd: float
    min_calmar: float
    min_trades: int
    min_profit_factor: float
    min_win_rate: float
    tolerances: dict[str, tuple[float, float, str]]


PROFILES = {
    "standard": AdmissionProfile(
        min_sharpe=0.20,
        max_mdd=0.35,
        min_calmar=0.15,
        min_trades=3,
        min_profit_factor=1.00,
        min_win_rate=0.40,
        tolerances={
            "cum_return": (0.08, 0.25, "required"),
            "sharpe": (0.35, 0.35, "required"),
            "mdd": (0.06, 0.30, "required"),
            "trades": (8.0, 0.50, "warning"),
        },
    ),
    "institutional": AdmissionProfile(
        min_sharpe=0.35,
        max_mdd=0.25,
        min_calmar=0.25,
        min_trades=5,
        min_profit_factor=1.05,
        min_win_rate=0.45,
        tolerances={
            "cum_return": (0.05, 0.20, "required"),
            "sharpe": (0.25, 0.25, "required"),
            "mdd": (0.04, 0.20, "required"),
            "trades": (5.0, 0.35, "warning"),
            "profit_factor": (0.20, 0.20, "warning"),
        },
    ),
}

_SCOPE_PARAMETERS = {
    "ticker", "symbol", "start", "end", "dockerImage", "benchmarkSymbol",
    "assetClass", "market", "venue", "resolution", "dataType", "source", "provider",
    "providerSource", "initialCash", "initial_cash", "cash", "name", "projectId",
    "ashareStatusFile", "strategySnapshotDir", "strategySnapshotMainFile",
    "strategySnapshotAlgorithmClass", "strategySnapshotLanguage", "datasetVersion",
    "datasetCertified", "datasetProduction", "datasetEnvironment", "datasetQaStatus",
    "datasetQaReportId", "allowResearchSource", "preflight",
}


def admission_config() -> dict[str, Any]:
    return {
        "profileVersion": PROFILE_VERSION,
        "stages": list(STAGE_SEQUENCE),
        "requiredRegimes": sorted(REQUIRED_REGIMES),
        "profiles": {
            name: {
                "minSharpe": profile.min_sharpe,
                "maxDrawdown": profile.max_mdd,
                "minCalmar": profile.min_calmar,
                "minTrades": profile.min_trades,
                "minProfitFactor": profile.min_profit_factor,
                "minWinRate": profile.min_win_rate,
            }
            for name, profile in PROFILES.items()
        },
        "sampleSets": {"seed_v1": SEED_SAMPLE_SET},
    }


def parameters_sha256(parameters: dict[str, Any]) -> str:
    strategy_parameters = {key: parameters[key] for key in sorted(parameters) if key not in _SCOPE_PARAMETERS}
    strategy_parameters.setdefault("feeModel", "default")
    strategy_parameters.setdefault("slippageModel", "default")
    payload = json.dumps(strategy_parameters, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _float(value: Any, *, percent: bool = False) -> float | None:
    if value in (None, "", "-"):
        return None
    text = str(value).strip().replace(",", "").replace("$", "")
    has_percent = text.endswith("%")
    if has_percent:
        text = text[:-1]
    try:
        result = float(text)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result / 100.0 if has_percent or percent else result


def normalize_metrics(summary: dict[str, Any], performance: dict[str, Any]) -> dict[str, float | None]:
    win_rate = _float(summary.get("Win Rate"))
    profit_factor = _float(summary.get("Profit-Loss Ratio"))
    if profit_factor == 0 and win_rate == 1:
        # LEAN reports zero when no losing trade exists; use a finite sentinel
        # so the payload stays strict-JSON while preserving the intended rank.
        profit_factor = 999999.0
    annual_return = _float(summary.get("Compounding Annual Return"))
    drawdown = abs(_float(summary.get("Drawdown")) or 0.0)
    return {
        "cum_return": _float(performance.get("strategy_return")) if performance.get("strategy_return") is not None else _float(summary.get("Net Profit")),
        "ann_return": annual_return,
        "sharpe": _float(performance.get("sharpe_recomputed_from_equity")) if performance.get("sharpe_recomputed_from_equity") is not None else _float(summary.get("Sharpe Ratio")),
        "mdd": drawdown,
        "calmar": _float(performance.get("calmar")) if performance.get("calmar") is not None else (annual_return / drawdown if annual_return is not None and drawdown > 0 else None),
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "expectancy": _float(summary.get("Expectancy")),
        "trades": _float(summary.get("Total Trades") or summary.get("Total Orders")),
    }


def _load_run(run_id: str, strategy_id: str) -> dict[str, Any]:
    with db() as connection:
        row = connection.execute(
            """
            select br.id, br.project_id, br.status, br.parameters_json, br.validation_json,
                   br.fingerprint_json, result.summary_metrics_json, result.performance_json,
                   experiment.strategy_version_id, experiment.parameter_hash
            from backtest_runs br
            left join backtest_results result on result.job_id = br.id
            left join experiments experiment on experiment.run_id = br.id
            where br.id = ?
            """,
            (run_id,),
        ).fetchone()
    item = row_to_dict(row)
    if not item:
        raise KeyError(f"Backtest run not found: {run_id}")
    if item.get("project_id") != strategy_id:
        raise ValueError(f"Backtest run {run_id} does not belong to strategy {strategy_id}.")
    if item.get("status") not in {"success", "succeeded"}:
        raise ValueError(f"Backtest run {run_id} is not successful.")
    if not item.get("summary_metrics"):
        raise ValueError(f"Backtest run {run_id} has no persisted result metrics.")
    item["metrics"] = normalize_metrics(item.get("summary_metrics") or {}, item.get("performance") or {})
    item["validationPassed"] = bool((item.get("validation") or {}).get("passed"))
    item["strategyParametersSha256"] = parameters_sha256(item.get("parameters") or {})
    return item


def _load_runs(strategy_id: str, run_ids: list[str], regimes: dict[str, str]) -> list[dict[str, Any]]:
    if not run_ids:
        raise ValueError("At least one completed run is required.")
    if len(run_ids) != len(set(run_ids)):
        raise ValueError("runIds must be unique.")
    missing_regime = [run_id for run_id in run_ids if regimes.get(run_id) not in REQUIRED_REGIMES | {"mixed"}]
    if missing_regime:
        raise ValueError(f"Every run must have a valid regime: {', '.join(missing_regime)}")
    covered = {regimes[run_id] for run_id in run_ids}
    if not REQUIRED_REGIMES <= covered:
        raise ValueError(f"Missing required regimes: {', '.join(sorted(REQUIRED_REGIMES - covered))}")
    runs = [_load_run(run_id, strategy_id) for run_id in run_ids]
    if any(not item.get("strategy_version_id") for item in runs):
        raise ValueError("Every admission run must have a persisted strategy version.")
    versions = {item["strategy_version_id"] for item in runs}
    if len(versions) != 1:
        raise ValueError("All admission runs must use the same strategy version.")
    parameter_hashes = {item["strategyParametersSha256"] for item in runs}
    if len(parameter_hashes) != 1:
        raise ValueError("All admission runs must use the same strategy parameter set.")
    return runs


def _aggregate(runs: list[dict[str, Any]]) -> dict[str, float | None]:
    keys = ("cum_return", "ann_return", "sharpe", "mdd", "calmar", "win_rate", "profit_factor", "expectancy")
    result: dict[str, float | None] = {}
    for key in keys:
        values = [float(item["metrics"][key]) for item in runs if item["metrics"].get(key) is not None]
        result[key] = mean(values) if values else None
    result["mdd"] = max((float(item["metrics"]["mdd"]) for item in runs if item["metrics"].get("mdd") is not None), default=None)
    result["trades"] = sum(float(item["metrics"].get("trades") or 0) for item in runs)
    return result


def _run_snapshot(runs: list[dict[str, Any]], regimes: dict[str, str]) -> list[dict[str, Any]]:
    return [
        {
            "runId": item["id"],
            "regime": regimes[item["id"]],
            "metrics": item["metrics"],
            "validationPassed": item["validationPassed"],
        }
        for item in runs
    ]


def _event(admission_id: str, stage: str, source_id: str | None, payload: dict[str, Any]) -> None:
    with db() as connection:
        connection.execute(
            "insert into strategy_admission_events (id, admission_id, stage, source_id, payload_json, created_at) values (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), admission_id, stage, source_id, json_dump(payload), utc_now()),
        )


def register_baseline(
    strategy_id: str,
    *,
    run_ids: list[str],
    regimes: dict[str, str],
    parameters: dict[str, Any],
    profile_name: str = "institutional",
    sample_set: str = "seed_v1",
) -> dict[str, Any]:
    if profile_name not in PROFILES:
        raise ValueError(f"Unknown admission profile: {profile_name}")
    runs = _load_runs(strategy_id, run_ids, regimes)
    parameter_hash = parameters_sha256(parameters)
    if any(item["strategyParametersSha256"] != parameter_hash for item in runs):
        raise ValueError("Submitted parameters do not match the admission runs.")
    invalid = [item["id"] for item in runs if not item["validationPassed"]]
    if invalid:
        raise ValueError(f"Baseline runs failed trusted-backtest validation: {', '.join(invalid)}")
    now = utc_now()
    admission_id = str(uuid.uuid4())
    snapshot = {
        "schemaVersion": 1,
        "sampleSet": sample_set,
        "registeredAt": now,
        "runs": _run_snapshot(runs, regimes),
        "aggregate": _aggregate(runs),
    }
    with db() as connection:
        existing = connection.execute(
            "select id from strategy_admissions where strategy_id = ? and parameters_sha256 = ? and profile_name = ? and profile_version = ?",
            (strategy_id, parameter_hash, profile_name, PROFILE_VERSION),
        ).fetchone()
        existing_item = row_to_dict(existing)
        if existing_item:
            admission_id = existing_item["id"]
            connection.execute(
                """
                update strategy_admissions
                set strategy_version_id = ?, sample_set = ?, current_stage = ?, baseline_snapshot_json = ?,
                    evaluation_json = ?, updated_at = ? where id = ?
                """,
                (runs[0].get("strategy_version_id"), sample_set, "baseline_registered", json_dump(snapshot), json_dump({}), now, admission_id),
            )
        else:
            connection.execute(
                """
                insert into strategy_admissions
                    (id, strategy_id, strategy_version_id, parameters_sha256, profile_name, profile_version,
                     sample_set, current_stage, baseline_snapshot_json, evaluation_json, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (admission_id, strategy_id, runs[0].get("strategy_version_id"), parameter_hash, profile_name,
                 PROFILE_VERSION, sample_set, "baseline_registered", json_dump(snapshot), json_dump({}), now, now),
            )
    _event(admission_id, "baseline_registered", run_ids[0], {"runIds": run_ids, "aggregate": snapshot["aggregate"]})
    return get_admission(strategy_id, parameter_hash, profile_name)


def _threshold_gate(name: str, actual: float | None, expected: str, passed: bool) -> dict[str, Any]:
    return {"name": name, "actual": actual, "expected": expected, "severity": "required", "passed": bool(passed)}


def _regression_gates(actual: dict[str, Any], baseline: dict[str, Any], profile: AdmissionProfile) -> list[dict[str, Any]]:
    gates = []
    for metric, (absolute, relative, severity) in profile.tolerances.items():
        current = actual.get(metric)
        expected = baseline.get(metric)
        if current is None or expected is None or not math.isfinite(float(current)) or not math.isfinite(float(expected)):
            gates.append({"name": f"baseline_drift:{metric}", "actual": current, "baseline": expected, "severity": severity, "passed": False, "reason": "metric_missing"})
            continue
        drift = abs(float(current) - float(expected))
        allowed = max(absolute, abs(float(expected)) * relative)
        gates.append({"name": f"baseline_drift:{metric}", "actual": current, "baseline": expected, "drift": drift, "allowed": allowed, "severity": severity, "passed": drift <= allowed})
    return gates


def evaluate_admission(
    strategy_id: str,
    *,
    run_ids: list[str],
    regimes: dict[str, str],
    parameters: dict[str, Any],
    profile_name: str = "institutional",
) -> dict[str, Any]:
    if profile_name not in PROFILES:
        raise ValueError(f"Unknown admission profile: {profile_name}")
    parameter_hash = parameters_sha256(parameters)
    admission = get_admission(strategy_id, parameter_hash, profile_name)
    if not admission:
        raise KeyError("A registered baseline was not found for this strategy, parameter set, and profile.")
    runs = _load_runs(strategy_id, run_ids, regimes)
    if any(item["strategyParametersSha256"] != parameter_hash for item in runs):
        raise ValueError("Submitted parameters do not match the admission runs.")
    profile = PROFILES[profile_name]
    aggregate = _aggregate(runs)
    gates = [
        _threshold_gate("trusted_backtests", 1.0 if all(item["validationPassed"] for item in runs) else 0.0, "all runs pass validation", all(item["validationPassed"] for item in runs)),
        _threshold_gate("min_sharpe", aggregate["sharpe"], f">= {profile.min_sharpe}", aggregate["sharpe"] is not None and aggregate["sharpe"] >= profile.min_sharpe),
        _threshold_gate("max_drawdown", aggregate["mdd"], f"<= {profile.max_mdd}", aggregate["mdd"] is not None and aggregate["mdd"] <= profile.max_mdd),
        _threshold_gate("min_calmar", aggregate["calmar"], f">= {profile.min_calmar}", aggregate["calmar"] is not None and aggregate["calmar"] >= profile.min_calmar),
        _threshold_gate("min_trades", aggregate["trades"], f">= {profile.min_trades}", aggregate["trades"] is not None and aggregate["trades"] >= profile.min_trades),
        _threshold_gate("min_profit_factor", aggregate["profit_factor"], f">= {profile.min_profit_factor}", aggregate["profit_factor"] is not None and aggregate["profit_factor"] >= profile.min_profit_factor),
        _threshold_gate("min_win_rate", aggregate["win_rate"], f">= {profile.min_win_rate}", aggregate["win_rate"] is not None and aggregate["win_rate"] >= profile.min_win_rate),
    ]
    gates.extend(_regression_gates(aggregate, (admission.get("baselineSnapshot") or {}).get("aggregate") or {}, profile))
    required_failed = [gate for gate in gates if gate["severity"] == "required" and not gate["passed"]]
    warning_failed = [gate for gate in gates if gate["severity"] == "warning" and not gate["passed"]]
    status = "fail" if required_failed else ("watch" if warning_failed else "pass")
    stage = "admission_passed" if status in {"pass", "watch"} else "baseline_registered"
    evaluation = {
        "schemaVersion": 1,
        "evaluatedAt": utc_now(),
        "status": status,
        "stage": stage,
        "runs": _run_snapshot(runs, regimes),
        "aggregate": aggregate,
        "gates": gates,
    }
    with db() as connection:
        connection.execute(
            "update strategy_admissions set current_stage = ?, evaluation_json = ?, updated_at = ? where id = ?",
            (stage, json_dump(evaluation), utc_now(), admission["id"]),
        )
    _event(admission["id"], stage, run_ids[0], {"runIds": run_ids, "status": status, "failed": [gate["name"] for gate in required_failed]})
    return get_admission(strategy_id, parameter_hash, profile_name)


def validate_paper_stage(
    strategy_id: str,
    *,
    session_id: str,
    parameters: dict[str, Any],
    profile_name: str = "institutional",
    min_report_days: int = 20,
) -> dict[str, Any]:
    if profile_name not in PROFILES:
        raise ValueError(f"Unknown admission profile: {profile_name}")
    if min_report_days < 1:
        raise ValueError("minReportDays must be at least 1.")
    parameter_hash = parameters_sha256(parameters)
    admission = get_admission(strategy_id, parameter_hash, profile_name)
    if not admission:
        raise KeyError("A strategy admission was not found for this parameter set and profile.")
    if admission.get("current_stage") not in {"admission_passed", "paper_validated"}:
        raise ValueError("Strategy admission must pass before paper validation.")
    with db() as connection:
        session_row = connection.execute(
            "select * from paper_sessions where id = ?",
            (session_id,),
        ).fetchone()
        report_rows = connection.execute(
            "select trade_date, qa_json from paper_daily_reports where session_id = ? order by trade_date asc",
            (session_id,),
        ).fetchall()
    session = row_to_dict(session_row)
    if not session:
        raise KeyError(f"Paper session not found: {session_id}")
    if session.get("project_id") != strategy_id:
        raise ValueError("Paper session does not belong to this strategy.")
    if session.get("status") != "stopped":
        raise ValueError("Paper session must be stopped before validation.")
    reports = [row_to_dict(row) or {} for row in report_rows]
    if len(reports) < min_report_days:
        raise ValueError(f"Paper validation requires at least {min_report_days} daily reports.")
    critical_dates = []
    for report in reports:
        qa = report.get("qa") or {}
        severity = str(qa.get("severity") or qa.get("status") or "ok").lower()
        if severity in {"critical", "failed", "fail", "error"} or qa.get("passed") is False:
            critical_dates.append(str(report.get("trade_date")))
    if critical_dates:
        raise ValueError(f"Paper validation has critical QA reports: {', '.join(critical_dates[:10])}")
    payload = {
        "sessionId": session_id,
        "reportDays": len(reports),
        "firstTradeDate": reports[0].get("trade_date"),
        "lastTradeDate": reports[-1].get("trade_date"),
        "validatedAt": utc_now(),
    }
    with db() as connection:
        connection.execute(
            "update strategy_admissions set current_stage = ?, updated_at = ? where id = ?",
            ("paper_validated", utc_now(), admission["id"]),
        )
    _event(admission["id"], "paper_validated", session_id, payload)
    return get_admission(strategy_id, parameter_hash, profile_name)


def get_admission(strategy_id: str, parameter_hash: str, profile_name: str = "institutional") -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute(
            """
            select * from strategy_admissions
            where strategy_id = ? and parameters_sha256 = ? and profile_name = ? and profile_version = ?
            """,
            (strategy_id, parameter_hash, profile_name, PROFILE_VERSION),
        ).fetchone()
    item = row_to_dict(row)
    if not item:
        return None
    with db() as connection:
        events = connection.execute(
            "select * from strategy_admission_events where admission_id = ? order by created_at asc",
            (item["id"],),
        ).fetchall()
    item["events"] = [row_to_dict(event) for event in events]
    return item


def admission_for_run(run_id: str, profile_name: str = "institutional") -> dict[str, Any]:
    if profile_name not in PROFILES:
        raise ValueError(f"Unknown admission profile: {profile_name}")
    with db() as connection:
        row = connection.execute(
            "select project_id, parameters_json from backtest_runs where id = ?",
            (run_id,),
        ).fetchone()
    run = row_to_dict(row)
    if not run:
        raise KeyError(f"Backtest run not found: {run_id}")
    strategy_id = run.get("project_id")
    parameter_hash = parameters_sha256(run.get("parameters") or {})
    admission = get_admission(str(strategy_id), parameter_hash, profile_name) if strategy_id else None
    return {
        "runId": run_id,
        "strategyId": strategy_id,
        "parametersSha256": parameter_hash,
        "profile": profile_name,
        "registrationStatus": (
            "not_applicable"
            if not strategy_id
            else "not_registered"
            if not admission
            else "registered"
        ),
        "admission": admission,
    }
