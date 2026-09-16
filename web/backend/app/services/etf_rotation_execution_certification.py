from __future__ import annotations

import json
import math
from collections import defaultdict
from typing import Any, Mapping, Sequence

from ..db import db, row_to_dict, rows_to_dicts
from ..repositories.backtest_repository import get_backtest, get_result
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
SUCCESS_STATES = {"success", "succeeded", "completed", "complete", "passed"}
REQUIRED_COST_FIELDS = ("fees", "slippage", "cashDrag", "capacityImpact")


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(loaded) if isinstance(loaded, Mapping) else {}
    return {}


def _sequence(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _passed_status(value: Any) -> bool:
    return _text(value).lower() in SUCCESS_STATES


def _nested_number(sources: Sequence[Mapping[str, Any]], aliases: Sequence[str]) -> float | None:
    lowered = {alias.lower(): alias for alias in aliases}
    for source in sources:
        for key, value in source.items():
            if str(key).lower() in lowered:
                number = _finite(value)
                if number is not None:
                    return number
    return None


def _validation_passed(run: Mapping[str, Any]) -> bool:
    validation = _mapping(run.get("validation") or run.get("validation_json"))
    return bool(validation.get("passed"))


def _data_release_id(run: Mapping[str, Any]) -> str:
    parameters = _mapping(run.get("parameters") or run.get("parameters_json"))
    return _text(
        run.get("data_release_id")
        or run.get("dataset_release_id")
        or parameters.get("dataReleaseId")
        or parameters.get("datasetReleaseId")
    )


def _metrics(result: Mapping[str, Any]) -> dict[str, Any]:
    summary = _mapping(result.get("summary_metrics") or result.get("summary_metrics_json"))
    stats = _mapping(result.get("statistics") or result.get("statistics_json"))
    performance = _mapping(result.get("performance") or result.get("performance_json"))
    sources = (summary, stats, performance)
    sharpe = _nested_number(sources, ("sharpe", "sharpe ratio", "sharperatio"))
    drawdown = _nested_number(
        sources, ("maxDrawdown", "maximum drawdown", "drawdown", "max_drawdown")
    )
    turnover = _nested_number(
        sources, ("turnover", "portfolio turnover", "portfolioTurnover", "totalTurnover")
    )
    trades = _nested_number(
        sources, ("tradeCount", "total trades", "totalTrades", "trades")
    )
    if trades is None:
        trades = float(len(_sequence(result.get("trades") or result.get("trades_json"))))
    return {
        "sharpe": sharpe,
        "maxDrawdown": drawdown,
        "turnover": turnover,
        "tradeCount": trades,
    }


def _cost_attribution(result: Mapping[str, Any]) -> dict[str, Any]:
    performance = _mapping(result.get("performance") or result.get("performance_json"))
    summary = _mapping(result.get("summary_metrics") or result.get("summary_metrics_json"))
    attribution = _mapping(
        performance.get("executionAttribution")
        or performance.get("execution_attribution")
        or summary.get("executionAttribution")
    )
    values = {
        "fees": _nested_number((attribution,), ("fees", "feeCost", "commission")),
        "slippage": _nested_number((attribution,), ("slippage", "slippageCost")),
        "cashDrag": _nested_number((attribution,), ("cashDrag", "cash_drag")),
        "capacityImpact": _nested_number(
            (attribution,), ("capacityImpact", "capacity_impact", "marketImpact")
        ),
    }
    return {
        **values,
        "complete": all(values[key] is not None for key in REQUIRED_COST_FIELDS),
        "source": "backtest_results.performance.executionAttribution" if attribution else None,
    }


def collect_backtest_run_evidence(
    run_id: str,
    *,
    code_version: str,
    cost_model_id: str,
) -> dict[str, Any]:
    run = get_backtest(run_id)
    if not run:
        return {
            "runId": run_id,
            "present": False,
            "failureReason": "backtest_run_missing",
        }
    result = get_result(run_id) or {}
    metrics = _metrics(result)
    fingerprint = _mapping(run.get("fingerprint") or run.get("fingerprint_json"))
    runtime = _mapping(run.get("runtime_identity") or run.get("runtime_identity_json"))
    return {
        "runId": run_id,
        "present": True,
        "status": run.get("status"),
        "validationPassed": _validation_passed(run),
        "dataReleaseId": _data_release_id(run),
        "codeVersion": _text(code_version),
        "costModelId": _text(cost_model_id),
        "metrics": metrics,
        "costAttribution": _cost_attribution(result),
        "durationSeconds": _finite(run.get("duration_seconds")),
        "runtimeIdentity": runtime,
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
        run_row = connection.execute(
            "select * from walk_forward_runs where id=?", (walk_forward_run_id,)
        ).fetchone()
        rows = connection.execute(
            """
            select * from walk_forward_windows
            where walk_forward_run_id=? order by fold,project_id,symbol
            """,
            (walk_forward_run_id,),
        ).fetchall()
    run = row_to_dict(run_row) or {}
    windows = rows_to_dicts(rows)
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
    decisions = list_constraint_decisions(session_id)
    fills = list_fills(session_id)
    ledger = list_ledger_entries(session_id)
    reconciliations = list_reconciliations(session_id)
    transitions = {
        _text(item.get("id")): list_transitions(_text(item.get("id")))
        for item in intents
        if _text(item.get("id"))
    }
    return {
        "sessionId": session_id,
        "intents": intents,
        "constraintDecisions": decisions,
        "fills": fills,
        "ledgerEntries": ledger,
        "transitionsByIntent": transitions,
        "reconciliations": reconciliations,
        "ledgerProjection": ledger_projection(session_id),
    }


def collect_admission_evidence(
    strategy_id: str,
    parameter_hash: str,
    *,
    profile_name: str = "institutional",
) -> dict[str, Any]:
    admission = get_admission(strategy_id, parameter_hash, profile_name)
    return admission or {
        "strategy_id": strategy_id,
        "parameters_sha256": parameter_hash,
        "profile_name": profile_name,
        "stage": "missing",
    }


def collect_resource_evidence() -> dict[str, Any]:
    return {
        "evidenceType": "runtime_snapshot",
        "snapshot": collect_resource_snapshot(),
    }


def _normalized_backtest_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "metrics": dict(payload.get("metrics") or {}),
        "lineage": {
            "codeVersion": _text(payload.get("codeVersion")),
            "dataReleaseId": _text(payload.get("dataReleaseId")),
            "costModelId": _text(payload.get("costModelId")),
        },
    }


def _walk_forward_check(
    evidence: Mapping[str, Any],
    *,
    data_release_id: str,
) -> tuple[bool, list[str], dict[str, Any]]:
    failures: list[str] = []
    windows = [dict(item) for item in _sequence(evidence.get("windows")) if isinstance(item, Mapping)]
    if not evidence.get("present"):
        failures.append("walk_forward_missing")
    if not windows:
        failures.append("walk_forward_windows_missing")
    if _text(evidence.get("lineageStatus")).lower() not in {"complete", "passed"}:
        failures.append("walk_forward_lineage_incomplete")

    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for window in windows:
        try:
            fold = int(window.get("fold"))
        except (TypeError, ValueError):
            failures.append("walk_forward_fold_invalid")
            continue
        grouped[fold].append(window)

    fold_summaries: list[dict[str, Any]] = []
    for fold, items in sorted(grouped.items()):
        boundary_sets = {
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
        if len(boundary_sets) != 1:
            failures.append(f"walk_forward_fold_{fold}_boundary_drift")
            continue
        (
            train_start,
            train_end,
            validation_start,
            validation_end,
            oos_start,
            oos_end,
            fold_fingerprint,
            dataset_version,
        ) = next(iter(boundary_sets))
        ordered = bool(
            train_start
            and train_end
            and validation_start
            and validation_end
            and oos_start
            and oos_end
            and train_start <= train_end < validation_start <= validation_end < oos_start <= oos_end
        )
        if not ordered:
            failures.append(f"walk_forward_fold_{fold}_window_order")
        if not fold_fingerprint:
            failures.append(f"walk_forward_fold_{fold}_fingerprint_missing")
        if dataset_version and dataset_version != data_release_id:
            failures.append(f"walk_forward_fold_{fold}_data_release_mismatch")
        statuses = {_text(item.get("status")).lower() for item in items}
        if statuses and not statuses.intersection(SUCCESS_STATES):
            failures.append(f"walk_forward_fold_{fold}_oos_not_completed")
        fold_summaries.append(
            {
                "fold": fold,
                "train": [train_start, train_end],
                "validation": [validation_start, validation_end],
                "oos": [oos_start, oos_end],
                "foldFingerprint": fold_fingerprint,
                "statuses": sorted(statuses),
            }
        )
    return not failures, failures, {"folds": fold_summaries, "count": len(grouped)}


def _paper_check(evidence: Mapping[str, Any]) -> tuple[bool, list[str], dict[str, Any]]:
    failures: list[str] = []
    intents = [dict(item) for item in _sequence(evidence.get("intents")) if isinstance(item, Mapping)]
    decisions = [dict(item) for item in _sequence(evidence.get("constraintDecisions")) if isinstance(item, Mapping)]
    fills = [dict(item) for item in _sequence(evidence.get("fills")) if isinstance(item, Mapping)]
    ledger = [dict(item) for item in _sequence(evidence.get("ledgerEntries")) if isinstance(item, Mapping)]
    reconciliations = [
        dict(item) for item in _sequence(evidence.get("reconciliations")) if isinstance(item, Mapping)
    ]

    if not intents:
        failures.append("paper_intents_missing")
    decisions_by_intent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for decision in decisions:
        decisions_by_intent[_text(decision.get("intent_id") or decision.get("intentId"))].append(decision)
    fills_by_intent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fill in fills:
        fills_by_intent[_text(fill.get("intent_id") or fill.get("intentId"))].append(fill)
    ledger_by_fill: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in ledger:
        ledger_by_fill[_text(entry.get("fill_id") or entry.get("fillId"))].append(entry)

    accepted = rejected = 0
    for intent in intents:
        intent_id = _text(intent.get("id"))
        related = decisions_by_intent.get(intent_id, [])
        if not related:
            failures.append(f"paper_intent_{intent_id}_constraint_decision_missing")
            continue
        outcomes = {
            _text(item.get("decision") or item.get("outcome") or item.get("status")).upper()
            for item in related
        }
        is_rejected = bool(outcomes.intersection({"REJECT", "REJECTED", "BLOCKED"}))
        is_accepted = bool(outcomes.intersection({"ACCEPT", "ACCEPTED", "APPROVED", "PASS", "PASSED"}))
        if is_rejected:
            rejected += 1
            if fills_by_intent.get(intent_id):
                failures.append(f"paper_intent_{intent_id}_rejection_has_fill")
        if is_accepted:
            accepted += 1

    for fill in fills:
        fill_id = _text(fill.get("id"))
        if len(ledger_by_fill.get(fill_id, [])) < 3:
            failures.append(f"paper_fill_{fill_id}_ledger_incomplete")

    if fills and not ledger:
        failures.append("paper_ledger_missing")
    if not reconciliations:
        failures.append("paper_reconciliation_missing")
    else:
        for item in reconciliations:
            status = _text(item.get("status") or item.get("result")).lower()
            passed = item.get("passed")
            if passed is False or (status and status not in SUCCESS_STATES):
                failures.append("paper_reconciliation_failed")
                break

    projection = _mapping(evidence.get("ledgerProjection"))
    if not projection or projection.get("error"):
        failures.append("ledger_projection_missing_or_invalid")

    idempotency = _mapping(evidence.get("idempotency"))
    if not idempotency:
        failures.append("ledger_idempotency_evidence_missing")
    else:
        before = idempotency.get("entryCountBefore")
        after = idempotency.get("entryCountAfter")
        same_digest = bool(idempotency.get("sameDigest") or idempotency.get("sameIds"))
        if before is None or after is None or int(before) != int(after) or not same_digest:
            failures.append("ledger_idempotency_not_proven")

    return (
        not failures,
        failures,
        {
            "intentCount": len(intents),
            "acceptedIntentCount": accepted,
            "rejectedIntentCount": rejected,
            "fillCount": len(fills),
            "ledgerEntryCount": len(ledger),
            "reconciliationCount": len(reconciliations),
        },
    )


def _resource_check(evidence: Mapping[str, Any]) -> tuple[bool, list[str], dict[str, Any]]:
    failures: list[str] = []
    snapshots: list[dict[str, Any]] = []
    for key in ("before", "after", "snapshot"):
        value = evidence.get(key)
        if isinstance(value, Mapping):
            snapshots.append(dict(value))
    if _text(evidence.get("evidenceType")) != "runtime_snapshot":
        failures.append("resource_evidence_not_runtime_snapshot")
    if not snapshots:
        failures.append("resource_snapshot_missing")
        return False, failures, {"snapshotCount": 0}

    memory_complete = any(
        _finite(_mapping(item.get("memory")).get("usedBytes")) is not None
        and (
            _finite(_mapping(item.get("memory")).get("processRssBytes")) is not None
            or _finite(_mapping(item.get("memory")).get("rssBytes")) is not None
        )
        for item in snapshots
    )
    cpu_complete = any(
        _finite(_mapping(item.get("cpu")).get("cpuCount")) is not None
        and _finite(_mapping(item.get("cpu")).get("usedPercent")) is not None
        for item in snapshots
    )
    if not memory_complete:
        failures.append("resource_memory_evidence_incomplete")
    if not cpu_complete:
        failures.append("resource_cpu_evidence_incomplete")
    duration = _finite(evidence.get("durationSeconds"))
    if duration is None or duration < 0:
        failures.append("resource_duration_missing")
    return not failures, failures, {"snapshotCount": len(snapshots), "durationSeconds": duration}


def _admission_check(evidence: Mapping[str, Any]) -> tuple[bool, list[str], dict[str, Any]]:
    stage = _text(evidence.get("stage") or evidence.get("status")).lower()
    passed = stage in {"admission_passed", "paper_validated"}
    failures = [] if passed else ["strategy_admission_not_passed"]
    return passed, failures, {"stage": stage}


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
        check(
            f"{label}_run_success",
            _passed_status(payload.get("status")),
            status=payload.get("status"),
        )
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
            all(_finite(metrics.get(key)) is not None for key in ("sharpe", "maxDrawdown", "turnover", "tradeCount")),
            metrics=metrics,
        )
        cost = _mapping(payload.get("costAttribution"))
        check(
            f"{label}_cost_attribution_complete",
            bool(cost.get("complete"))
            and all(_finite(cost.get(key)) is not None for key in REQUIRED_COST_FIELDS),
            costAttribution=cost,
        )

    base_report: dict[str, Any] | None = None
    try:
        base_report = build_certification_report(
            candidate=_normalized_backtest_payload(candidate),
            baseline=_normalized_backtest_payload(baseline),
            gates=gates or {},
            deterministic_fingerprints=deterministic_fingerprints,
        )
    except ValueError as exc:
        check("strategy_metric_certification_valid", False, error=str(exc))
    else:
        check(
            "strategy_metric_certification_valid",
            bool(base_report.get("passed")),
            failureReasons=base_report.get("failureReasons") or [],
        )

    wf_passed, wf_failures, wf_summary = _walk_forward_check(
        walk_forward, data_release_id=release_id
    )
    check("walk_forward_complete", wf_passed, failureReasons=wf_failures, **wf_summary)

    paper_passed, paper_failures, paper_summary = _paper_check(paper)
    check("paper_execution_chain_complete", paper_passed, failureReasons=paper_failures, **paper_summary)

    admission_passed, admission_failures, admission_summary = _admission_check(admission)
    check("admission_passed", admission_passed, failureReasons=admission_failures, **admission_summary)

    resources_with_duration = dict(resources)
    resources_with_duration.setdefault("durationSeconds", candidate.get("durationSeconds"))
    resource_passed, resource_failures, resource_summary = _resource_check(resources_with_duration)
    check("resource_evidence_complete", resource_passed, failureReasons=resource_failures, **resource_summary)

    failures = list(dict.fromkeys(failures))
    deterministic = {
        "dataReleaseId": release_id,
        "candidate": {
            "runId": candidate.get("runId"),
            "dataReleaseId": candidate.get("dataReleaseId"),
            "metrics": candidate.get("metrics"),
            "costAttribution": candidate.get("costAttribution"),
            "canonicalConfigSha256": candidate.get("canonicalConfigSha256"),
            "runFingerprint": candidate.get("runFingerprint"),
        },
        "baseline": {
            "runId": baseline.get("runId"),
            "dataReleaseId": baseline.get("dataReleaseId"),
            "metrics": baseline.get("metrics"),
            "costAttribution": baseline.get("costAttribution"),
            "canonicalConfigSha256": baseline.get("canonicalConfigSha256"),
            "runFingerprint": baseline.get("runFingerprint"),
        },
        "walkForward": wf_summary,
        "paper": paper_summary,
        "admission": admission_summary,
        "resources": resource_summary,
        "checks": [{"name": item["name"], "passed": item["passed"]} for item in checks],
    }
    return {
        "schemaVersion": SCHEMA_VERSION,
        "certified": not failures,
        "failureReasons": failures,
        "dataReleaseId": release_id,
        "checks": checks,
        "strategyCertification": base_report,
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
