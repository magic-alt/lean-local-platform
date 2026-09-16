from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date
from typing import Any, Callable, Mapping

from ..db import db
from ..repositories.backtest_repository import get_backtest, get_result
from .backtest_service import create_backtest_job
from .data_releases import get_data_release
from .etf_rotation_certification import canonical_fingerprint
from .etf_rotation_execution_attribution import materialize_execution_attribution
from .etf_rotation_execution_certification import (
    build_execution_certification,
    collect_admission_evidence,
    collect_backtest_run_evidence,
    collect_paper_evidence,
    collect_walk_forward_evidence,
    register_execution_certification_artifact,
)
from .experiment_batches import create_batch, detail as experiment_batch_detail
from .experiments import get_experiment_versions
from .paper import finalize_walkforward_run
from .paper_order_pipeline import list_ledger_entries
from .projects import create_project, get_project
from .resource_pressure import collect_resource_snapshot
from .strategy_admission import parameters_sha256
from .workflows import record_workflow_event, workflow_detail


SCHEMA_VERSION = "etf-rotation-certification-campaign.v1"
WORKFLOW_PREFIX = "etf-rotation-certification:"
TERMINAL_BACKTEST = {"success", "failed", "cancelled"}
TERMINAL_BATCH = {"success", "failed", "cancelled", "partial"}

BacktestDispatcher = Callable[[dict[str, Any]], None]
BatchDispatcher = Callable[[dict[str, Any]], None]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _event(campaign_id: str, stage: str, action: str, status: str, **details: Any) -> dict[str, Any]:
    return record_workflow_event(
        workflow_id=campaign_id,
        trace_id=campaign_id,
        stage=stage,
        action=action,
        status=status,
        resource_type="etf_rotation_certification_campaign",
        resource_id=campaign_id,
        details=details,
    )


def _events(campaign_id: str) -> list[dict[str, Any]]:
    return list(workflow_detail(campaign_id).get("events") or [])


def _action_event(events: list[dict[str, Any]], action: str) -> dict[str, Any] | None:
    return next((item for item in reversed(events) if item.get("action") == action), None)


def _details(event: Mapping[str, Any] | None) -> dict[str, Any]:
    if not event:
        return {}
    value = event.get("details")
    return dict(value) if isinstance(value, Mapping) else {}


def _campaign_config(events: list[dict[str, Any]]) -> dict[str, Any]:
    created = next((item for item in events if item.get("action") == "campaign_created"), None)
    config = _details(created).get("config") if created else None
    if not isinstance(config, Mapping):
        raise ValueError("ETF certification campaign is missing its frozen configuration.")
    return dict(config)


def _normalize_symbols(value: Any) -> list[str]:
    raw = value.split(",") if isinstance(value, str) else list(value or [])
    symbols: list[str] = []
    for item in raw:
        symbol = str(item).strip().upper()
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    if len(symbols) < 2:
        raise ValueError("ETF certification campaign requires at least two symbols.")
    return symbols


def _validate_release(config: Mapping[str, Any]) -> dict[str, Any]:
    release_id = _text(config.get("dataReleaseId"))
    if not release_id:
        raise ValueError("dataReleaseId is required; campaigns never select a mutable latest release.")
    release = get_data_release(release_id)
    if not release:
        raise ValueError(f"Immutable DataRelease not found: {release_id}")
    if _text(release.get("status")).lower() != "active":
        raise ValueError(f"DataRelease is not active: {release_id}")
    market = _text(release.get("market")).lower()
    if market and market != "usa":
        raise ValueError(f"ETF certification requires a USA DataRelease, got {market}.")
    start = _text(config.get("start"))
    end = _text(config.get("end"))
    coverage_start = _text(release.get("coverage_start"))
    coverage_end = _text(release.get("coverage_end"))
    if coverage_start and start and start < coverage_start:
        raise ValueError(f"Campaign start {start} precedes DataRelease coverage {coverage_start}.")
    if coverage_end and end and end > coverage_end:
        raise ValueError(f"Campaign end {end} exceeds DataRelease coverage {coverage_end}.")
    return release


def _normalize_config(config: Mapping[str, Any]) -> dict[str, Any]:
    frozen = dict(config)
    project_id = _text(frozen.get("projectId"))
    if not project_id:
        raise ValueError("projectId is required.")
    project = get_project(project_id)
    project_config = dict(project.get("config") or {})
    if _text(project_config.get("templateKey")) != "etf_rotation":
        raise ValueError("The certification candidate project must use templateKey=etf_rotation.")
    if _text(project_config.get("market") or "usa").lower() != "usa":
        raise ValueError("The ETF certification candidate project must use market=usa.")
    symbols = _normalize_symbols(frozen.get("symbols") or (frozen.get("parameters") or {}).get("symbols"))
    start = _text(frozen.get("start"))
    end = _text(frozen.get("end"))
    if not start or not end or date.fromisoformat(end) < date.fromisoformat(start):
        raise ValueError("Campaign start/end must be ordered ISO dates.")
    frozen.update(
        {
            "projectId": project_id,
            "symbols": symbols,
            "symbol": _text(frozen.get("symbol") or symbols[0]).upper(),
            "start": start,
            "end": end,
            "cash": float(frozen.get("cash") or 100000),
            "benchmarkSymbol": _text(frozen.get("benchmarkSymbol") or symbols[0]).upper(),
            "costModelId": _text(frozen.get("costModelId") or "lean-constant-fee-slippage-v1"),
            "profileName": _text(frozen.get("profileName") or "institutional"),
        }
    )
    parameters = dict(project_config.get("parameters") or {})
    parameters.update(dict(frozen.get("parameters") or {}))
    parameters.update(
        {
            "symbols": ",".join(symbols),
            "dataReleaseId": _text(frozen.get("dataReleaseId")),
            "costModelId": frozen["costModelId"],
        }
    )
    frozen["parameters"] = parameters
    walk_forward = dict(frozen.get("walkForward") or {})
    required = ("universeVersion", "adjustmentContract", "featurePipelineVersion")
    missing = [key for key in required if not _text(walk_forward.get(key))]
    if missing:
        raise ValueError("walkForward is missing frozen lineage fields: " + ", ".join(missing))
    frozen["walkForward"] = walk_forward
    _validate_release(frozen)
    return frozen


def start_campaign(config: Mapping[str, Any]) -> dict[str, Any]:
    frozen = _normalize_config(config)
    campaign_id = f"{WORKFLOW_PREFIX}{uuid.uuid4()}"
    release = _validate_release(frozen)
    _event(
        campaign_id,
        "campaign",
        "campaign_created",
        "created",
        schemaVersion=SCHEMA_VERSION,
        config=frozen,
        dataRelease={
            key: release.get(key)
            for key in ("id", "profile", "market", "coverage_start", "coverage_end", "as_of_time", "manifest_sha256")
        },
    )
    return campaign_status(campaign_id)


def _base_request(config: Mapping[str, Any], project_id: str, *, name: str) -> dict[str, Any]:
    return {
        "projectId": project_id,
        "symbol": config["symbol"],
        "name": name,
        "assetClass": "equity",
        "market": "usa",
        "venue": "usa",
        "resolution": "daily",
        "dataType": "trade",
        "start": config["start"],
        "end": config["end"],
        "cash": config["cash"],
        "benchmarkSymbol": config["benchmarkSymbol"],
        "parameters": dict(config["parameters"]),
    }


def _dispatch_backtest(
    campaign_id: str,
    events: list[dict[str, Any]],
    *,
    action: str,
    role: str,
    request: dict[str, Any],
    dispatcher: BacktestDispatcher,
) -> dict[str, Any]:
    existing = _action_event(events, action)
    if existing:
        run_id = _text(_details(existing).get("runId"))
        return get_backtest(run_id) or {"id": run_id, "status": "missing"}
    job = create_backtest_job(request)
    dispatcher(job)
    _event(
        campaign_id,
        "backtest",
        action,
        "queued",
        role=role,
        runId=job["id"],
        taskId=job.get("task_id"),
        canonicalConfigSha256=job.get("canonical_config_sha256"),
    )
    return job


def _result_fingerprint(run_id: str) -> str:
    run = get_backtest(run_id) or {}
    result = get_result(run_id) or {}
    return canonical_fingerprint(
        {
            "canonicalConfigSha256": run.get("canonical_config_sha256"),
            "dataReleaseId": run.get("data_release_id") or (run.get("parameters") or {}).get("dataReleaseId"),
            "statistics": result.get("statistics") or {},
            "summaryMetrics": result.get("summary_metrics") or {},
            "orders": result.get("orders") or [],
            "trades": result.get("trades") or [],
            "holdings": result.get("holdings") or [],
        }
    )


def _ensure_terminal_backtest(
    campaign_id: str,
    events: list[dict[str, Any]],
    *,
    dispatch_action: str,
    complete_action: str,
    role: str,
) -> tuple[str, dict[str, Any] | None]:
    event = _action_event(events, dispatch_action)
    run_id = _text(_details(event).get("runId"))
    run = get_backtest(run_id) if run_id else None
    if not run:
        return "missing", None
    status = _text(run.get("status")).lower()
    if status not in TERMINAL_BACKTEST:
        return "waiting", run
    if status != "success":
        if not _action_event(events, f"{role}_failed"):
            _event(campaign_id, "backtest", f"{role}_failed", "failed", runId=run_id, status=status, error=run.get("error_message") or run.get("error"))
        return "failed", run
    materialized = materialize_execution_attribution(run_id)
    if not materialized.get("complete"):
        if not _action_event(events, f"{role}_attribution_incomplete"):
            _event(campaign_id, "attribution", f"{role}_attribution_incomplete", "blocked", runId=run_id, attribution=materialized)
        return "blocked", run
    if not _action_event(events, complete_action):
        _event(
            campaign_id,
            "backtest",
            complete_action,
            "success",
            role=role,
            runId=run_id,
            resultFingerprint=_result_fingerprint(run_id),
            attribution=materialized,
        )
    return "success", get_backtest(run_id)


def _baseline_project(campaign_id: str, events: list[dict[str, Any]], config: Mapping[str, Any]) -> str:
    existing = _action_event(events, "baseline_project_created")
    if existing:
        return _text(_details(existing).get("projectId"))
    project = create_project(
        name=f"ETF Certification Static Baseline {campaign_id.rsplit(':', 1)[-1][:8]}",
        language="Python",
        template_key="etf_static_equal_weight",
        market="usa",
        asset_class="equity",
        venue="usa",
        resolution="daily",
        data_type="trade",
        parameters={
            "symbols": ",".join(config["symbols"]),
            "commissionPerOrder": config["parameters"].get("commissionPerOrder", 1.0),
            "slippageBps": config["parameters"].get("slippageBps", 2.0),
            "costModelId": config["costModelId"],
        },
    )
    _event(campaign_id, "baseline", "baseline_project_created", "success", projectId=project["id"])
    return str(project["id"])


def _candidate_snapshot_request(config: Mapping[str, Any], candidate_run: Mapping[str, Any], *, name: str) -> dict[str, Any]:
    request = _base_request(config, str(config["projectId"]), name=name)
    params = dict(candidate_run.get("parameters") or {})
    for source_key, target_key in (
        ("strategySnapshotDir", "strategySnapshotSourceDir"),
        ("strategySnapshotMainFile", "strategySnapshotMainFile"),
        ("strategySnapshotAlgorithmClass", "strategySnapshotAlgorithmClass"),
        ("strategySnapshotLanguage", "strategySnapshotLanguage"),
    ):
        if params.get(source_key):
            request[target_key] = params[source_key]
    return request


def _walk_forward_config(config: Mapping[str, Any]) -> dict[str, Any]:
    wf = dict(config["walkForward"])
    parameters = dict(config["parameters"])
    parameters["dataReleaseId"] = config["dataReleaseId"]
    return {
        "kind": "backtest",
        "mode": "walk_forward",
        "name": f"ETF certification walk-forward {config['dataReleaseId'][:18]}",
        "projectId": config["projectId"],
        "symbols": [config["symbol"]],
        "assetClass": "equity",
        "market": "usa",
        "venue": "usa",
        "resolution": "daily",
        "dataType": "trade",
        "start": config["start"],
        "end": config["end"],
        "cash": config["cash"],
        "benchmarkSymbol": config["benchmarkSymbol"],
        "parameters": parameters,
        "parameterGrid": wf.get("parameterGrid") or {},
        "trainYears": int(wf.get("trainYears") or 3),
        "testYears": int(wf.get("testYears") or 1),
        "stepYears": int(wf.get("stepYears") or 1),
        "validationMonths": int(wf.get("validationMonths") or 6),
        "datasetVersion": config["dataReleaseId"],
        "universeVersion": wf["universeVersion"],
        "adjustmentContract": wf["adjustmentContract"],
        "featurePipelineVersion": wf["featurePipelineVersion"],
        "selectionMetric": wf.get("selectionMetric") or "validationSharpe",
        "objective": wf.get("objective") or "sharpe",
    }


def _walk_forward_run_id(batch_id: str) -> str | None:
    with db() as connection:
        row = connection.execute("select id from walk_forward_runs where batch_id=?", (batch_id,)).fetchone()
    return str(row["id"]) if row else None


def _ledger_digest(session_id: str) -> tuple[int, str]:
    rows = list_ledger_entries(session_id)
    identity = [
        {
            "id": item.get("id"),
            "intentId": item.get("intent_id"),
            "fillId": item.get("fill_id"),
            "entryType": item.get("entry_type"),
            "amount": str(item.get("precise_amount") or item.get("amount") or "0"),
            "quantity": str(item.get("precise_quantity") or item.get("quantity") or "0"),
            "idempotencyKey": item.get("idempotency_key"),
        }
        for item in rows
    ]
    return len(rows), hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _paper_with_idempotency(session_id: str) -> dict[str, Any]:
    evidence = collect_paper_evidence(session_id)
    decisions = {str(item.get("decision") or "").upper() for item in evidence.get("constraintDecisions") or []}
    if not {"ACCEPT", "REJECT"}.issubset(decisions):
        evidence["campaignBlocker"] = "paper_requires_real_accept_and_reject"
        return evidence
    with db() as connection:
        row = connection.execute(
            """
            select id from paper_walkforward_runs
            where session_id=? and status='success'
            order by finished_at desc,trade_date desc limit 1
            """,
            (session_id,),
        ).fetchone()
    if not row:
        evidence["campaignBlocker"] = "paper_successful_walkforward_run_missing"
        return evidence
    paper_run_id = str(row["id"])
    before_count, before_digest = _ledger_digest(session_id)
    finalize_walkforward_run(paper_run_id)
    after_count, after_digest = _ledger_digest(session_id)
    evidence["idempotency"] = {
        "paperRunId": paper_run_id,
        "entryCountBefore": before_count,
        "entryCountAfter": after_count,
        "digestBefore": before_digest,
        "digestAfter": after_digest,
        "sameDigest": before_digest == after_digest,
    }
    return evidence


def _container_digest(run: Mapping[str, Any]) -> str:
    fingerprint = dict(run.get("fingerprint") or {})
    docker = fingerprint.get("docker") if isinstance(fingerprint.get("docker"), Mapping) else {}
    runtime = run.get("runtime_identity") if isinstance(run.get("runtime_identity"), Mapping) else {}
    return _text((docker or {}).get("digest") or (docker or {}).get("image") or (runtime or {}).get("runtimeSha256") or run.get("docker_image"))


def _git_commit(run: Mapping[str, Any]) -> str:
    fingerprint = dict(run.get("fingerprint") or {})
    git = fingerprint.get("git") if isinstance(fingerprint.get("git"), Mapping) else {}
    return _text((git or {}).get("commit"))


def campaign_status(campaign_id: str) -> dict[str, Any]:
    events = _events(campaign_id)
    config = _campaign_config(events)
    latest = events[-1] if events else {}
    details = _details(latest)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "campaignId": campaign_id,
        "status": latest.get("status"),
        "stage": latest.get("stage"),
        "action": latest.get("action"),
        "dataReleaseId": config.get("dataReleaseId"),
        "projectId": config.get("projectId"),
        "details": details,
        "events": events,
    }


def advance_campaign(
    campaign_id: str,
    *,
    dispatch_backtest: BacktestDispatcher,
    dispatch_batch: BatchDispatcher,
) -> dict[str, Any]:
    events = _events(campaign_id)
    config = _campaign_config(events)
    release = _validate_release(config)
    if _action_event(events, "artifact_registered"):
        return campaign_status(campaign_id)

    before = _action_event(events, "resource_before_captured")
    if not before:
        _event(campaign_id, "resources", "resource_before_captured", "success", snapshot=collect_resource_snapshot(), scope="platform_runtime_envelope")
        events = _events(campaign_id)

    candidate = _dispatch_backtest(
        campaign_id,
        events,
        action="canonical_dispatched",
        role="canonical",
        request=_base_request(config, str(config["projectId"]), name=f"ETF certification canonical {campaign_id[-8:]}"),
        dispatcher=dispatch_backtest,
    )
    events = _events(campaign_id)
    state, candidate = _ensure_terminal_backtest(
        campaign_id,
        events,
        dispatch_action="canonical_dispatched",
        complete_action="canonical_completed",
        role="canonical",
    )
    if state != "success" or not candidate:
        return campaign_status(campaign_id)
    events = _events(campaign_id)

    if not _action_event(events, "resource_after_captured"):
        _event(campaign_id, "resources", "resource_after_captured", "success", snapshot=collect_resource_snapshot(), scope="platform_runtime_envelope", durationSeconds=candidate.get("duration_seconds"))
        events = _events(campaign_id)

    rerun = _dispatch_backtest(
        campaign_id,
        events,
        action="rerun_dispatched",
        role="deterministic_rerun",
        request=_candidate_snapshot_request(config, candidate, name=f"ETF certification deterministic rerun {campaign_id[-8:]}"),
        dispatcher=dispatch_backtest,
    )
    events = _events(campaign_id)
    state, rerun = _ensure_terminal_backtest(
        campaign_id,
        events,
        dispatch_action="rerun_dispatched",
        complete_action="rerun_completed",
        role="rerun",
    )
    if state != "success" or not rerun:
        return campaign_status(campaign_id)
    events = _events(campaign_id)
    candidate_fp = _result_fingerprint(str(candidate["id"]))
    rerun_fp = _result_fingerprint(str(rerun["id"]))
    if candidate_fp != rerun_fp:
        if not _action_event(events, "deterministic_replay_failed"):
            _event(campaign_id, "determinism", "deterministic_replay_failed", "failed", candidateFingerprint=candidate_fp, rerunFingerprint=rerun_fp)
        return campaign_status(campaign_id)
    if not _action_event(events, "deterministic_replay_verified"):
        _event(campaign_id, "determinism", "deterministic_replay_verified", "success", fingerprint=candidate_fp)
        events = _events(campaign_id)

    baseline_project_id = _baseline_project(campaign_id, events, config)
    events = _events(campaign_id)
    baseline_request = _base_request(config, baseline_project_id, name=f"ETF certification static baseline {campaign_id[-8:]}")
    baseline_request["parameters"] = {
        "symbols": ",".join(config["symbols"]),
        "dataReleaseId": config["dataReleaseId"],
        "commissionPerOrder": config["parameters"].get("commissionPerOrder", 1.0),
        "slippageBps": config["parameters"].get("slippageBps", 2.0),
        "costModelId": config["costModelId"],
    }
    _dispatch_backtest(
        campaign_id,
        events,
        action="baseline_dispatched",
        role="static_equal_weight",
        request=baseline_request,
        dispatcher=dispatch_backtest,
    )
    events = _events(campaign_id)
    state, baseline = _ensure_terminal_backtest(
        campaign_id,
        events,
        dispatch_action="baseline_dispatched",
        complete_action="baseline_completed",
        role="baseline",
    )
    if state != "success" or not baseline:
        return campaign_status(campaign_id)
    events = _events(campaign_id)

    batch_event = _action_event(events, "walk_forward_dispatched")
    if not batch_event:
        batch = create_batch(_walk_forward_config(config))
        dispatch_batch(batch)
        _event(campaign_id, "walk_forward", "walk_forward_dispatched", "queued", batchId=batch["id"], total=batch.get("total"))
        return campaign_status(campaign_id)
    batch_id = _text(_details(batch_event).get("batchId"))
    batch = experiment_batch_detail(batch_id)
    batch_status = _text(batch.get("status")).lower()
    if batch_status not in TERMINAL_BATCH:
        return campaign_status(campaign_id)
    if batch_status != "success":
        if not _action_event(events, "walk_forward_failed"):
            _event(campaign_id, "walk_forward", "walk_forward_failed", "failed", batchId=batch_id, status=batch_status, summary=batch.get("summary") or {})
        return campaign_status(campaign_id)
    walk_forward_run_id = _walk_forward_run_id(batch_id)
    if not walk_forward_run_id:
        _event(campaign_id, "walk_forward", "walk_forward_evidence_missing", "failed", batchId=batch_id)
        return campaign_status(campaign_id)
    if not _action_event(events, "walk_forward_completed"):
        _event(campaign_id, "walk_forward", "walk_forward_completed", "success", batchId=batch_id, walkForwardRunId=walk_forward_run_id)
        events = _events(campaign_id)

    paper_session_id = _text(config.get("paperSessionId"))
    if not paper_session_id:
        if not _action_event(events, "waiting_paper_evidence"):
            _event(
                campaign_id,
                "paper",
                "waiting_paper_evidence",
                "blocked",
                reason="authoritative_paper_v2_session_required",
                note="Current canonical ETF strategy uses USA; attach only a real Paper-v2 session after that execution scope is certified. Synthetic or shadow ledgers are prohibited.",
            )
        return campaign_status(campaign_id)
    paper_evidence = _paper_with_idempotency(paper_session_id)
    if paper_evidence.get("campaignBlocker"):
        _event(campaign_id, "paper", "paper_evidence_incomplete", "blocked", reason=paper_evidence["campaignBlocker"], sessionId=paper_session_id)
        return campaign_status(campaign_id)
    if not _action_event(events, "paper_replay_verified"):
        _event(campaign_id, "paper", "paper_replay_verified", "success", sessionId=paper_session_id, idempotency=paper_evidence.get("idempotency"))
        events = _events(campaign_id)

    versions = get_experiment_versions(str(candidate["id"])) or {}
    experiment = dict(versions.get("experiment") or {})
    parameter_hash = _text(experiment.get("parameter_hash")) or parameters_sha256(candidate.get("parameters") or {})
    admission = collect_admission_evidence(str(config["projectId"]), parameter_hash, profile_name=str(config["profileName"]))
    admission = {**admission, "stage": admission.get("current_stage") or admission.get("stage")}

    candidate_evidence = collect_backtest_run_evidence(str(candidate["id"]), code_version=_git_commit(candidate), cost_model_id=str(config["costModelId"]))
    baseline_evidence = collect_backtest_run_evidence(str(baseline["id"]), code_version=_git_commit(baseline), cost_model_id=str(config["costModelId"]))
    walk_forward_evidence = collect_walk_forward_evidence(walk_forward_run_id)
    before_snapshot = _details(_action_event(events, "resource_before_captured")).get("snapshot")
    after_event = _action_event(events, "resource_after_captured")
    after_snapshot = _details(after_event).get("snapshot")
    resources = {
        "evidenceType": "runtime_snapshot",
        "scope": "platform_runtime_envelope",
        "before": before_snapshot,
        "after": after_snapshot,
        "durationSeconds": candidate.get("duration_seconds"),
    }
    report = build_execution_certification(
        data_release_id=str(config["dataReleaseId"]),
        candidate=candidate_evidence,
        baseline=baseline_evidence,
        walk_forward=walk_forward_evidence,
        paper=paper_evidence,
        admission=admission,
        resources=resources,
        gates=dict(config.get("gates") or {}),
        deterministic_fingerprints=[candidate_fp, rerun_fp],
    )
    if not report.get("certified"):
        _event(campaign_id, "certification", "certification_failed", "failed", report=report)
        return campaign_status(campaign_id)
    artifact = register_execution_certification_artifact(
        report,
        git_commit=_git_commit(candidate),
        container_digest=_container_digest(candidate),
        as_of_time=_text(release.get("as_of_time")),
        timezone="UTC",
        currency="USD",
    )
    _event(campaign_id, "certification", "artifact_registered", "success", artifactId=artifact["artifactId"], artifactFingerprint=report["artifactFingerprint"], report=report)
    return campaign_status(campaign_id)
