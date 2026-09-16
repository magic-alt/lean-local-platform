from __future__ import annotations

import json
import math
from collections import defaultdict
from typing import Any, Mapping, Sequence

from ..db import db, row_to_dict, rows_to_dicts
from ..repositories.backtest_repository import get_backtest, get_result
from .artifact_registry import register_platform_artifact
from .etf_rotation_certification import build_certification_report, canonical_fingerprint
from .paper_order_pipeline import (
    ledger_projection,
    list_constraint_decisions,
    list_fills,
    list_intents,
    list_ledger_entries,
    list_reconciliations,
    list_transitions,
)
from .resource_pressure import collect_resource_snapshot
from .strategy_admission import get_admission

SCHEMA_VERSION = "etf-rotation-execution-certification.v1"
SUCCESS_STATES = {
    "success", "succeeded", "completed", "complete", "passed", "oos_completed"
}
REQUIRED_COST_FIELDS = ("fees", "slippage", "cashDrag", "capacityImpact")


def _map(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _success(value: Any) -> bool:
    return _text(value).lower() in SUCCESS_STATES


def _find_number(sources: Sequence[Mapping[str, Any]], aliases: Sequence[str]) -> float | None:
    wanted = {name.lower() for name in aliases}
    for source in sources:
        for key, value in source.items():
            if str(key).lower() in wanted and (number := _number(value)) is not None:
                return number
    return None


def _release_id(run: Mapping[str, Any]) -> str:
    params = _map(run.get("parameters") or run.get("parameters_json"))
    return _text(
        run.get("data_release_id")
        or run.get("dataset_release_id")
        or params.get("dataReleaseId")
        or params.get("datasetReleaseId")
    )


def _result_metrics(result: Mapping[str, Any]) -> dict[str, Any]:
    summary = _map(result.get("summary_metrics") or result.get("summary_metrics_json"))
    stats = _map(result.get("statistics") or result.get("statistics_json"))
    performance = _map(result.get("performance") or result.get("performance_json"))
    sources = (summary, stats, performance)
    trades = _find_number(sources, ("tradeCount", "total trades", "totalTrades", "trades"))
    if trades is None:
        trades = float(len(_list(result.get("trades") or result.get("trades_json"))))
    return {
        "sharpe": _find_number(sources, ("sharpe", "sharpe ratio", "sharperatio")),
        "maxDrawdown": _find_number(
            sources, ("maxDrawdown", "maximum drawdown", "drawdown", "max_drawdown")
        ),
        "turnover": _find_number(
            sources, ("turnover", "portfolio turnover", "portfolioTurnover", "totalTurnover")
        ),
        "tradeCount": trades,
    }


def _costs(result: Mapping[str, Any]) -> dict[str, Any]:
    performance = _map(result.get("performance") or result.get("performance_json"))
    summary = _map(result.get("summary_metrics") or result.get("summary_metrics_json"))
    attribution = _map(
        performance.get("executionAttribution")
        or performance.get("execution_attribution")
        or summary.get("executionAttribution")
    )
    values = {
        "fees": _find_number((attribution,), ("fees", "feeCost", "commission")),
        "slippage": _find_number((attribution,), ("slippage", "slippageCost")),
        "cashDrag": _find_number((attribution,), ("cashDrag", "cash_drag")),
        "capacityImpact": _find_number(
            (attribution,), ("capacityImpact", "capacity_impact", "marketImpact")
        ),
    }
    return {
        **values,
        "complete": all(values[key] is not None for key in REQUIRED_COST_FIELDS),
        "source": "backtest_results.performance.executionAttribution" if attribution else None,
    }


def collect_backtest_run_evidence(
    run_id: str, *, code_version: str, cost_model_id: str
) -> dict[str, Any]:
    run = get_backtest(run_id)
    if not run:
        return {"runId": run_id, "present": False, "failureReason": "backtest_run_missing"}
    result = get_result(run_id) or {}
    validation = _map(run.get("validation") or run.get("validation_json"))
    fingerprint = _map(run.get("fingerprint") or run.get("fingerprint_json"))
    return {
        "runId": run_id,
        "present": True,
        "status": run.get("status"),
        "validationPassed": bool(validation.get("passed")),
        "dataReleaseId": _release_id(run),
        "codeVersion": _text(code_version),
        "costModelId": _text(cost_model_id),
        "metrics": _result_metrics(result),
        "costAttribution": _costs(result),
        "durationSeconds": _number(run.get("duration_seconds")),
        "runtimeIdentity": _map(
            run.get("runtime_identity") or run.get("runtime_identity_json")
        ),
        "canonicalConfigSha256": _text(run.get("canonical_config_sha256")),
        "runFingerprint": _text(
            fingerprint.get("fingerprint")
            or fingerprint.get("sha256")
            or fingerprint.get("runFingerprint")
        ),
        "resultPresent": bool(result),
    }


def collect_walk_forward_evidence(walk_forward_run_id: str) -> dict[str, Any]:
    with db() as connection:
        run = row_to_dict(
            connection.execute(
                "select * from walk_forward_runs where id=?", (walk_forward_run_id,)
            ).fetchone()
        ) or {}
        windows = rows_to_dicts(
            connection.execute(
                """
                select * from walk_forward_windows
                where walk_forward_run_id=? order by fold,project_id,symbol
                """,
                (walk_forward_run_id,),
            ).fetchall()
        )
    return {
        "runId": walk_forward_run_id,
        "present": bool(run),
        "status": run.get("status"),
        "datasetVersion": run.get("dataset_version"),
        "universeVersion": run.get("universe_version"),
        "adjustmentContract": run.get("adjustment_contract"),
        "featurePipelineVersion": run.get("feature_pipeline_version"),
        "lineageStatus": run.get("lineage_status"),
        "windows": windows,
    }


def collect_paper_evidence(session_id: str) -> dict[str, Any]:
    intents = list_intents(session_id)
    return {
        "sessionId": session_id,
        "intents": intents,
        "constraintDecisions": list_constraint_decisions(session_id),
        "fills": list_fills(session_id),
        "ledgerEntries": list_ledger_entries(session_id),
        "transitionsByIntent": {
            _text(item.get("id")): list_transitions(_text(item.get("id")))
            for item in intents
            if _text(item.get("id"))
        },
        "reconciliations": list_reconciliations(session_id),
        "ledgerProjection": ledger_projection(session_id),
    }


def collect_admission_evidence(
    strategy_id: str, parameter_hash: str, *, profile_name: str = "institutional"
) -> dict[str, Any]:
    return get_admission(strategy_id, parameter_hash, profile_name) or {
        "strategy_id": strategy_id,
        "parameters_sha256": parameter_hash,
        "profile_name": profile_name,
        "stage": "missing",
    }


def collect_resource_snapshot_evidence() -> dict[str, Any]:
    return {"evidenceType": "runtime_snapshot", "snapshot": collect_resource_snapshot()}


def _cert_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "metrics": dict(payload.get("metrics") or {}),
        "lineage": {
            "codeVersion": _text(payload.get("codeVersion")),
            "dataReleaseId": _text(payload.get("dataReleaseId")),
            "costModelId": _text(payload.get("costModelId")),
        },
    }


def _walk_forward_check(
    evidence: Mapping[str, Any], data_release_id: str
) -> tuple[list[str], dict[str, Any]]:
    failures: list[str] = []
    windows = [
        dict(item) for item in _list(evidence.get("windows")) if isinstance(item, Mapping)
    ]
    if not evidence.get("present"):
        failures.append("walk_forward_missing")
    if not _success(evidence.get("status")):
        failures.append("walk_forward_run_not_completed")
    if _text(evidence.get("datasetVersion")) != data_release_id:
        failures.append("walk_forward_data_release_mismatch")
    if _text(evidence.get("lineageStatus")).lower() not in {"complete", "passed"}:
        failures.append("walk_forward_lineage_incomplete")
    if not windows:
        failures.append("walk_forward_windows_missing")

    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for window in windows:
        try:
            grouped[int(window.get("fold"))].append(window)
        except (TypeError, ValueError):
            failures.append("walk_forward_fold_invalid")

    summaries: list[dict[str, Any]] = []
    for fold, items in sorted(grouped.items()):
        boundaries = {
            (
                _text(item.get("train_start")),
                _text(item.get("train_end")),
                _text(item.get("validation_start")),
                _text(item.get("validation_end")),
                _text(item.get("oos_start")),
                _text(item.get("oos_end")),
                _text(item.get("fold_fingerprint")),
                _text(item.get("dataset_version")),
            )
            for item in items
        }
        if len(boundaries) != 1:
            failures.append(f"walk_forward_fold_{fold}_boundary_drift")
            continue
        train_start, train_end, val_start, val_end, oos_start, oos_end, digest, release = next(iter(boundaries))
        ordered = bool(
            train_start and train_end and val_start and val_end and oos_start and oos_end
            and train_start <= train_end < val_start <= val_end < oos_start <= oos_end
        )
        if not ordered:
            failures.append(f"walk_forward_fold_{fold}_window_order")
        if not digest:
            failures.append(f"walk_forward_fold_{fold}_fingerprint_missing")
        if release != data_release_id:
            failures.append(f"walk_forward_fold_{fold}_data_release_mismatch")
        statuses = {_text(item.get("status")).lower() for item in items}
        if not statuses or not statuses.intersection(SUCCESS_STATES):
            failures.append(f"walk_forward_fold_{fold}_oos_not_completed")
        summaries.append(
            {
                "fold": fold,
                "train": [train_start, train_end],
                "validation": [val_start, val_end],
                "oos": [oos_start, oos_end],
                "foldFingerprint": digest,
                "statuses": sorted(statuses),
            }
        )
    return failures, {"folds": summaries, "count": len(grouped)}


def _paper_check(evidence: Mapping[str, Any]) -> tuple[list[str], dict[str, Any]]:
    failures: list[str] = []
    intents = [dict(x) for x in _list(evidence.get("intents")) if isinstance(x, Mapping)]
    decisions = [
        dict(x) for x in _list(evidence.get("constraintDecisions")) if isinstance(x, Mapping)
    ]
    fills = [dict(x) for x in _list(evidence.get("fills")) if isinstance(x, Mapping)]
    ledger = [
        dict(x) for x in _list(evidence.get("ledgerEntries")) if isinstance(x, Mapping)
    ]
    reconciliations = [
        dict(x) for x in _list(evidence.get("reconciliations")) if isinstance(x, Mapping)
    ]
    if not intents:
        failures.append("paper_intents_missing")

    by_intent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    fills_by_intent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    ledger_by_fill: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in decisions:
        by_intent[_text(item.get("intent_id") or item.get("intentId"))].append(item)
    for item in fills:
        fills_by_intent[_text(item.get("intent_id") or item.get("intentId"))].append(item)
    for item in ledger:
        ledger_by_fill[_text(item.get("fill_id") or item.get("fillId"))].append(item)

    accepted = rejected = 0
    for intent in intents:
        intent_id = _text(intent.get("id"))
        related = by_intent.get(intent_id, [])
        if not related:
            failures.append(f"paper_intent_{intent_id}_constraint_decision_missing")
            continue
        outcomes = {_text(item.get("decision")).upper() for item in related}
        if "REJECT" in outcomes:
            rejected += 1
            if fills_by_intent.get(intent_id):
                failures.append(f"paper_intent_{intent_id}_rejection_has_fill")
        if "ACCEPT" in outcomes:
            accepted += 1
    for fill in fills:
        fill_id = _text(fill.get("id"))
        if len(ledger_by_fill.get(fill_id, [])) < 3:
            failures.append(f"paper_fill_{fill_id}_ledger_incomplete")
    if fills and not ledger:
        failures.append("paper_ledger_missing")

    if not reconciliations:
        failures.append("paper_reconciliation_missing")
    elif any(
        item.get("passed") is False
        or (
            _text(item.get("status") or item.get("result"))
            and not _success(item.get("status") or item.get("result"))
        )
        for item in reconciliations
    ):
        failures.append("paper_reconciliation_failed")
    if not _map(evidence.get("ledgerProjection")):
        failures.append("ledger_projection_missing_or_invalid")

    idem = _map(evidence.get("idempotency"))
    if not idem:
        failures.append("ledger_idempotency_evidence_missing")
    else:
        before, after = idem.get("entryCountBefore"), idem.get("entryCountAfter")
        if (
            before is None
            or after is None
            or int(before) != int(after)
            or not bool(idem.get("sameDigest") or idem.get("sameIds"))
        ):
            failures.append("ledger_idempotency_not_proven")
    return failures, {
        "intentCount": len(intents),
        "acceptedIntentCount": accepted,
        "rejectedIntentCount": rejected,
        "fillCount": len(fills),
        "ledgerEntryCount": len(ledger),
        "reconciliationCount": len(reconciliations),
    }


def _resource_check(evidence: Mapping[str, Any]) -> tuple[list[str], dict[str, Any]]:
    failures: list[str] = []
    before, after = evidence.get("before"), evidence.get("after")
    snapshots = [dict(x) for x in (before, after) if isinstance(x, Mapping)]
    if _text(evidence.get("evidenceType")) != "runtime_snapshot":
        failures.append("resource_evidence_not_runtime_snapshot")
    if len(snapshots) != 2:
        failures.append("resource_before_after_snapshots_required")
    if not snapshots:
        return failures + ["resource_snapshot_missing"], {"snapshotCount": 0}
    if not any(
        _number(_map(x.get("memory")).get("usedBytes")) is not None
        and (
            _number(_map(x.get("memory")).get("processRssBytes")) is not None
            or _number(_map(x.get("memory")).get("rssBytes")) is not None
        )
        for x in snapshots
    ):
        failures.append("resource_memory_evidence_incomplete")
    if not any(
        _number(_map(x.get("cpu")).get("cpuCount")) is not None
        and _number(_map(x.get("cpu")).get("usedPercent")) is not None
        for x in snapshots
    ):
        failures.append("resource_cpu_evidence_incomplete")
    duration = _number(evidence.get("durationSeconds"))
    if duration is None or duration < 0:
        failures.append("resource_duration_missing")
    return failures, {"snapshotCount": len(snapshots), "durationSeconds": duration}


def build_execution_certification(
    *,
    data_release_id: str,
    candidate: Mapping[str, Any],
    baseline: Mapping[str, Any],
    walk_forward: Mapping[str, Any],
    paper: Mapping[str, Any],
    admission: Mapping[str, Any],
    resources: Mapping[str, Any],
    gates: Mapping[str, Any] | None = None,
    deterministic_fingerprints: Sequence[str] = (),
) -> dict[str, Any]:
    release_id = _text(data_release_id)
    checks: list[dict[str, Any]] = []
    failures: list[str] = []

    def check(name: str, passed: bool, **details: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "details": details})
        if not passed:
            failures.append(name)

    check("pinned_data_release_present", bool(release_id), dataReleaseId=release_id)
    for label, payload in (("candidate", candidate), ("baseline", baseline)):
        check(f"{label}_run_present", bool(payload.get("present")), runId=payload.get("runId"))
        check(f"{label}_run_success", _success(payload.get("status")), status=payload.get("status"))
        check(
            f"{label}_validation_passed",
            bool(payload.get("validationPassed")),
            validationPassed=payload.get("validationPassed"),
        )
        check(
            f"{label}_data_release_match",
            bool(release_id) and _text(payload.get("dataReleaseId")) == release_id,
            expected=release_id,
            actual=payload.get("dataReleaseId"),
        )
        metrics = dict(payload.get("metrics") or {})
        check(
            f"{label}_metrics_complete",
            all(
                _number(metrics.get(key)) is not None
                for key in ("sharpe", "maxDrawdown", "turnover", "tradeCount")
            ),
            metrics=metrics,
        )
        cost = _map(payload.get("costAttribution"))
        check(
            f"{label}_cost_attribution_complete",
            bool(cost.get("complete"))
            and all(_number(cost.get(key)) is not None for key in REQUIRED_COST_FIELDS),
            costAttribution=cost,
        )

    strategy_report: dict[str, Any] | None = None
    try:
        strategy_report = build_certification_report(
            candidate=_cert_payload(candidate),
            baseline=_cert_payload(baseline),
            gates=gates or {},
            deterministic_fingerprints=deterministic_fingerprints,
        )
    except ValueError as exc:
        check("strategy_metric_certification_valid", False, error=str(exc))
    else:
        check(
            "strategy_metric_certification_valid",
            bool(strategy_report.get("passed")),
            failureReasons=strategy_report.get("failureReasons") or [],
        )

    wf_failures, wf_summary = _walk_forward_check(walk_forward, release_id)
    check("walk_forward_complete", not wf_failures, failureReasons=wf_failures, **wf_summary)
    paper_failures, paper_summary = _paper_check(paper)
    check(
        "paper_execution_chain_complete",
        not paper_failures,
        failureReasons=paper_failures,
        **paper_summary,
    )
    admission_stage = _text(admission.get("stage") or admission.get("status")).lower()
    admission_ok = admission_stage in {"admission_passed", "paper_validated"}
    check(
        "admission_passed",
        admission_ok,
        failureReasons=[] if admission_ok else ["strategy_admission_not_passed"],
        stage=admission_stage,
    )
    runtime = dict(resources)
    runtime.setdefault("durationSeconds", candidate.get("durationSeconds"))
    resource_failures, resource_summary = _resource_check(runtime)
    check(
        "resource_evidence_complete",
        not resource_failures,
        failureReasons=resource_failures,
        **resource_summary,
    )

    failures = list(dict.fromkeys(failures))
    deterministic = {
        "dataReleaseId": release_id,
        "candidate": {
            key: candidate.get(key)
            for key in (
                "runId", "dataReleaseId", "metrics", "costAttribution",
                "canonicalConfigSha256", "runFingerprint",
            )
        },
        "baseline": {
            key: baseline.get(key)
            for key in (
                "runId", "dataReleaseId", "metrics", "costAttribution",
                "canonicalConfigSha256", "runFingerprint",
            )
        },
        "walkForward": wf_summary,
        "paper": paper_summary,
        "admission": {"stage": admission_stage},
        "resources": resource_summary,
        "checks": [{"name": x["name"], "passed": x["passed"]} for x in checks],
    }
    return {
        "schemaVersion": SCHEMA_VERSION,
        "certified": not failures,
        "failureReasons": failures,
        "dataReleaseId": release_id,
        "checks": checks,
        "strategyCertification": strategy_report,
        "evidence": {
            "candidate": dict(candidate),
            "baseline": dict(baseline),
            "walkForward": dict(walk_forward),
            "paper": dict(paper),
            "admission": dict(admission),
            "resources": dict(resources),
        },
        "artifactFingerprint": canonical_fingerprint(deterministic),
    }


def register_execution_certification_artifact(
    report: Mapping[str, Any],
    *,
    git_commit: str,
    container_digest: str,
    as_of_time: str,
    timezone: str = "UTC",
    currency: str = "USD",
    object_key: str | None = None,
) -> dict[str, Any]:
    if not report.get("certified"):
        raise ValueError("uncertified ETF execution evidence cannot enter artifact_registry")
    release_id = _text(report.get("dataReleaseId"))
    fingerprint = _text(report.get("artifactFingerprint"))
    if not release_id or not fingerprint:
        raise ValueError("certification artifact requires dataReleaseId and artifactFingerprint")
    evidence = _map(report.get("evidence"))
    artifact = {
        "artifactId": f"etf_exec_cert_{fingerprint[:24]}",
        "schemaVersion": SCHEMA_VERSION,
        "artifactType": "ETF_EXECUTION_CERTIFICATION",
        "promotionStatus": "LEAN_VALIDATED",
        "dataReleaseId": release_id,
        "gitCommit": _text(git_commit),
        "containerDigest": _text(container_digest),
        "asOfTime": _text(as_of_time),
        "timezone": _text(timezone) or "UTC",
        "currency": _text(currency) or "USD",
        "payloadSha256": canonical_fingerprint(dict(report)),
        "payloadRef": {"objectKey": object_key, "mediaType": "application/json"},
        "metadata": {
            "artifactFingerprint": fingerprint,
            "candidateRunId": _map(evidence.get("candidate")).get("runId"),
            "baselineRunId": _map(evidence.get("baseline")).get("runId"),
            "failureReasons": [],
        },
    }
    for key in ("gitCommit", "containerDigest", "asOfTime"):
        if not artifact[key]:
            raise ValueError(f"certification artifact requires {key}")
    with db() as connection:
        register_platform_artifact(connection, artifact)
    return artifact
