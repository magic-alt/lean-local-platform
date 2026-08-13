#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db import db, row_to_dict, rows_to_dicts  # noqa: E402
from app.services import market_lake  # noqa: E402
from app.lean_engine.errors import LeanPlatformError  # noqa: E402
from app.repositories.backtest_repository import get_backtest  # noqa: E402
from app.services.backtest_execution_validation import canonical_result_sha256  # noqa: E402
from app.services.backtest_preflight import prepare_backtest_request  # noqa: E402
from app.services.backtest_validation import build_backtest_validation  # noqa: E402
from app.services.data_sync import BULK_DATASET_KEYS, _sync_completion_evidence  # noqa: E402
from app.services.db_object_store import integrity_report  # noqa: E402
from app.services.run_paths import run_file  # noqa: E402
from app.services.source_gate import resolve_source_context, source_certification  # noqa: E402


RELEASE_DATE = "2026-07-25"
GOLDEN_PROJECT_ID = "audit-rev-20260723143400-20260723143400"
GOLDEN_PAYLOAD = {
    "projectId": GOLDEN_PROJECT_ID,
    "symbol": "600519",
    "assetClass": "equity",
    "market": "china",
    "start": "2026-06-01",
    "end": "2026-07-22",
    "cash": 1_000_000,
    "source": "tushare",
    "benchmarkSymbol": "000300",
    "executionPolicy": "next_open",
}
CSI_SAMPLE_DATES = [
    "2005-04-08",
    "2005-07-01",
    "2005-12-30",
    "2006-12-29",
    "2007-12-28",
    "2008-12-31",
    "2009-12-31",
    "2010-12-31",
    "2011-12-30",
    "2012-12-31",
    "2013-12-31",
    "2014-12-31",
    "2015-12-31",
    "2016-12-30",
    "2017-12-29",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _api_token() -> str:
    configured = os.environ.get("LEAN_API_TOKEN", "").strip()
    if configured:
        return configured
    token_path = Path(
        os.environ.get(
            "LEAN_API_TOKEN_FILE",
            str(ROOT / "web" / "runtime" / "secrets" / "api_token"),
        )
    )
    return token_path.read_text(encoding="utf-8").strip() if token_path.is_file() else ""


def _resolve_golden_project_id(requested: str | None) -> str:
    with db() as connection:
        if requested:
            row = connection.execute("select id from projects where id=?", (requested,)).fetchone()
            if not row:
                raise ValueError(f"Golden project does not exist: {requested}")
            return str(row["id"])
        rows = rows_to_dicts(
            connection.execute(
                """
                select project.id,run.validation_json
                from projects project
                join backtest_runs run on run.project_id=project.id
                where run.status='success'
                order by run.finished_at desc,run.created_at desc
                """
            ).fetchall()
        )
        for item in rows:
            if (item.get("validation") or {}).get("passed") is True:
                return str(item["id"])
        row = connection.execute(
            "select id from projects order by created_at desc limit 1"
        ).fetchone()
    if not row:
        raise ValueError("No project exists for the Golden Pair.")
    return str(row["id"])


def _api(
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: int = 60,
) -> tuple[int, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    token = _api_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return response.status, json.loads(raw.decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {"detail": raw}
        return exc.code, body


def _expected_rejection(name: str, operation: Callable[[], Any]) -> dict[str, Any]:
    try:
        operation()
    except Exception as exc:
        return {"name": name, "passed": True, "outcome": "rejected", "error": str(exc)}
    return {"name": name, "passed": False, "outcome": "unexpectedly_allowed"}


def source_qa_reference_matrix() -> dict[str, Any]:
    request = dict(GOLDEN_PAYLOAD)
    prepared = prepare_backtest_request(request, repair=False)
    parameters = prepared["parameters"]
    certification = source_certification(
        "tushare",
        asset_class="equity",
        market="china",
        venue="china",
    )
    benchmark = market_lake.aggregate(
        kind="bars", asset_class="index", market="china", venue="china", source="tushare",
        columns="count(*) as row_count,min(trade_date) as first_date,max(trade_date) as last_date",
        predicates=("symbol='000300'", "trade_date between ? and ?"),
        parameters=(parameters["start"], parameters["end"]),
    )
    benchmark["symbol"] = "000300"
    fingerprint = {
        "datasetCertification": certification,
        "data": {"benchmark": benchmark},
    }
    validation = build_backtest_validation(parameters, fingerprint)
    entries: list[dict[str, Any]] = [
        {
            "name": "certified_production_baseline",
            "passed": bool(prepared["preflight"].get("ready")) and bool(validation.get("passed")),
            "outcome": "allowed" if validation.get("passed") else "rejected",
            "gateResults": [
                {
                    "name": gate["name"],
                    "passed": gate["passed"],
                    "severity": gate["severity"],
                }
                for gate in validation.get("gates") or []
            ],
        }
    ]
    for source in ("baostock", "adata", "test", "forged-provider"):
        entries.append(
            _expected_rejection(
                f"uncertified_source_{source}",
                lambda source=source: resolve_source_context(
                    parameters,
                    source=source,
                    allow_research_source=False,
                    asset_class="equity",
                    market="china",
                    venue="china",
                ),
            )
        )

    forged_fingerprint = deepcopy(fingerprint)
    forged_fingerprint["datasetCertification"]["isCertified"] = False
    forged_validation = build_backtest_validation(parameters, forged_fingerprint)
    forged_source_gate = next(
        gate
        for gate in forged_validation["gates"]
        if gate["name"] == "production_source_certification"
    )
    entries.append(
        {
            "name": "forged_certification_flag",
            "passed": not forged_source_gate["passed"] and not forged_validation["passed"],
            "outcome": "rejected" if not forged_source_gate["passed"] else "allowed",
        }
    )

    injected_qa = {
        "symbol": "600519",
        "startDate": parameters["start"],
        "endDate": parameters["end"],
        "passed": False,
        "severity": "critical",
        "blockingReports": [{"id": "release-injected-critical"}],
    }
    with patch("app.services.backtest_preflight.quality_gate_range", return_value=injected_qa):
        entries.append(
            _expected_rejection(
                "critical_qa_report",
                lambda: prepare_backtest_request(request, repair=False),
            )
        )

    injected_reference = {
        "passed": False,
        "severity": "critical",
        "issues": ["release_injected_pit_gap"],
        "reference": {
            "passed": False,
            "severity": "critical",
            "issues": ["release_injected_pit_gap"],
        },
    }
    with patch("app.services.data_coverage.ashare_coverage", return_value=injected_reference):
        entries.append(
            _expected_rejection(
                "critical_reference_gap",
                lambda: prepare_backtest_request(request, repair=False),
            )
        )

    return {
        "schemaVersion": 1,
        "generatedAt": _utc_now(),
        "passed": all(item["passed"] for item in entries),
        "productionCertification": certification,
        "entries": entries,
    }


def csi300_evidence() -> dict[str, Any]:
    source_manifest_path = ROOT / "config" / "data-sources" / "csi300_pit_sources.json"
    bundle_dir = ROOT / "web" / "runtime" / "source-cache" / "csi300-official"
    bundle_manifest_path = bundle_dir / "bundle-manifest.json"
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    if not bundle_manifest_path.is_file():
        return {
            "schemaVersion": 1,
            "generatedAt": _utc_now(),
            "passed": False,
            "status": "not_available",
            "reason": "official_bundle_cache_missing",
            "sourceManifest": str(source_manifest_path.relative_to(ROOT)),
            "expectedBundleManifest": str(bundle_manifest_path.relative_to(ROOT)),
            "fetchCommand": (source_manifest.get("bundle") or {}).get("fetch_command"),
            "offlineVerifyCommand": (source_manifest.get("bundle") or {}).get(
                "offline_verify_command"
            ),
        }
    bundle_manifest = json.loads(bundle_manifest_path.read_text(encoding="utf-8"))
    file_checks = []
    for item in bundle_manifest["files"]:
        path = bundle_dir / item["path"]
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        file_checks.append(
            {
                "path": item["path"],
                "expectedSha256": item["sha256"],
                "actualSha256": actual,
                "passed": actual == item["sha256"],
            }
        )
    inventory_payload = json.dumps(
        bundle_manifest["files"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    recomputed_bundle_sha = hashlib.sha256(inventory_payload).hexdigest()

    with db() as connection:
        totals = row_to_dict(
            connection.execute(
                """
                select count(*) as intervals,count(distinct symbol) as symbols,
                       min(start_date) as start_date,max(coalesce(end_date,'9999-12-31')) as end_date
                from universe_membership where universe_code='CSI300'
                """
            ).fetchone()
        ) or {}
        event_count = int(
            connection.execute(
                "select count(*) as count from index_membership_events where index_code='CSI300'"
            ).fetchone()["count"]
        )
        artifact_count = int(
            connection.execute(
                "select count(*) as count from index_source_artifacts where index_code='CSI300'"
            ).fetchone()["count"]
        )
        samples = []
        for sample_date in CSI_SAMPLE_DATES:
            count = int(
                connection.execute(
                    """
                    select count(*) as count
                    from universe_membership
                    where universe_code='CSI300' and start_date <= ?
                      and (end_date is null or end_date >= ?)
                    """,
                    (sample_date, sample_date),
                ).fetchone()["count"]
            )
            samples.append({"date": sample_date, "memberCount": count, "passed": count == 300})

    manifest_bundle = source_manifest.get("bundle") or {}
    passed = all(
        (
            source_manifest.get("coverage_status") == "full_verified_official_bundle",
            source_manifest.get("coverage_start") == "2005-04-08",
            not source_manifest.get("initial_reconstruction", {}).get("current_constituent_substitution"),
            int(source_manifest.get("initial_reconstruction", {}).get("member_count") or 0) == 300,
            manifest_bundle.get("sha256") == bundle_manifest.get("bundleSha256"),
            recomputed_bundle_sha == bundle_manifest.get("bundleSha256"),
            all(item["passed"] for item in file_checks),
            str(totals.get("start_date")) == "2005-04-08",
            event_count == int(source_manifest.get("event_count") or 0),
            all(item["passed"] for item in samples),
        )
    )
    return {
        "schemaVersion": 1,
        "generatedAt": _utc_now(),
        "passed": passed,
        "sourceManifest": str(source_manifest_path.relative_to(ROOT)),
        "coverageStatus": source_manifest.get("coverage_status"),
        "coverageStart": source_manifest.get("coverage_start"),
        "currentConstituentSubstitution": source_manifest.get(
            "initial_reconstruction", {}
        ).get("current_constituent_substitution"),
        "fetchCommand": manifest_bundle.get("fetch_command"),
        "offlineVerifyCommand": manifest_bundle.get("offline_verify_command"),
        "bundle": {
            "fileCount": bundle_manifest.get("fileCount"),
            "expectedSha256": bundle_manifest.get("bundleSha256"),
            "recomputedSha256": recomputed_bundle_sha,
            "verifiedFileCount": sum(1 for item in file_checks if item["passed"]),
            "failedFiles": [item for item in file_checks if not item["passed"]],
        },
        "database": {
            **totals,
            "membershipEvents": event_count,
            "sourceArtifacts": artifact_count,
            "sampleDates": samples,
        },
    }


def archive_evidence(run_id: str) -> dict[str, Any]:
    completion = _sync_completion_evidence(run_id, set(BULK_DATASET_KEYS))
    integrity = integrity_report()
    with db() as connection:
        issue_status = rows_to_dicts(
            connection.execute(
                """
                select status,resolution_code,count(*) as count
                from provider_raw_archive_issues
                group by status,resolution_code
                order by status,resolution_code
                """
            ).fetchall()
        )
        open_count = int(
            connection.execute(
                """
                select count(*) as count from provider_raw_archive_issues
                where coalesce(status,'open')='open'
                """
            ).fetchone()["count"]
        )
    return {
        "schemaVersion": 1,
        "generatedAt": _utc_now(),
        "passed": bool(completion.get("passed")) and bool(integrity.get("passed")) and open_count == 0,
        "runId": run_id,
        "tenDatasetEvidence": completion,
        "activeObjectIntegrity": integrity,
        "archiveIssueStatus": issue_status,
        "remainingOpenCount": open_count,
    }


def _run_golden(base_url: str, run_id: str | None = None) -> dict[str, Any]:
    if run_id is None:
        status, created = _api(base_url, "POST", "/api/backtests", GOLDEN_PAYLOAD, timeout=120)
        if status >= 400 or not created.get("id"):
            raise RuntimeError(f"Golden creation failed: HTTP {status}: {created}")
        run_id = str(created["id"])
    final: dict[str, Any] = {}
    for _ in range(240):
        with db() as connection:
            row = connection.execute(
                """
                select status,error,error_message,started_at,finished_at
                from backtest_runs where id=?
                """,
                (run_id,),
            ).fetchone()
        if not row:
            raise RuntimeError(f"Golden run disappeared from canonical MySQL: {run_id}")
        run_status = dict(row)
        if run_status.get("status") in {"success", "failed", "cancelled"}:
            final = get_backtest(run_id) or {}
            break
        time.sleep(2)
    if final.get("status") != "success":
        raise RuntimeError(f"Golden run did not succeed: {run_id}: {final.get('error')}")

    validation = final.get("validation") or {}
    execution = validation.get("execution") or {}
    fingerprint = final.get("fingerprint") or {}
    result_path = run_file(
        run_id,
        final.get("result_json_path"),
        f"results/{run_id}.json",
    )
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    recomputed = canonical_result_sha256(payload)
    statistics = final.get("statistics") or {}
    return {
        "runId": run_id,
        "status": final.get("status"),
        "trustStatus": final.get("trust_status"),
        "trustReason": final.get("trust_reason"),
        "datasetReleaseId": final.get("dataset_release_id"),
        "reproducibilityCertificateId": final.get("reproducibility_certificate_id"),
        "validationPassed": validation.get("passed"),
        "inputFingerprint": fingerprint.get("inputFingerprint"),
        "canonicalResultSha256": execution.get("canonicalResultSha256"),
        "recomputedCanonicalResultSha256": recomputed,
        "rawResultSha256": execution.get("rawResultSha256"),
        "endingEquity": statistics.get("End Equity"),
        "fillCount": (execution.get("ledger") or {}).get("fillCount"),
        "completedDate": execution.get("completedDate"),
        "datasetVersion": fingerprint.get("datasetVersion"),
        "fileManifestSha256": (
            fingerprint.get("datasetCertification") or {}
        ).get("fileManifestSha256"),
        "gitCommit": fingerprint.get("git_commit"),
        "gitStatusHash": fingerprint.get("git_status_hash"),
        "canonicalRecomputePassed": recomputed == execution.get("canonicalResultSha256"),
    }


def golden_evidence(
    base_url: str,
    first_run_id: str | None = None,
    second_run_id: str | None = None,
) -> dict[str, Any]:
    # Keep all evidence in memory until both runs finish so repository status
    # and therefore the canonical input identity cannot change between runs.
    first = _run_golden(base_url, first_run_id)
    second = _run_golden(base_url, second_run_id)
    comparisons = {
        "inputFingerprint": first["inputFingerprint"] == second["inputFingerprint"],
        "canonicalResultSha256": first["canonicalResultSha256"] == second["canonicalResultSha256"],
        "endingEquity": first["endingEquity"] == second["endingEquity"],
        "fillCount": first["fillCount"] == second["fillCount"],
        "completedDate": first["completedDate"] == second["completedDate"],
        "datasetVersion": first["datasetVersion"] == second["datasetVersion"],
        "datasetReleaseId": first["datasetReleaseId"] == second["datasetReleaseId"],
        "gitIdentity": (
            first["gitCommit"],
            first["gitStatusHash"],
        )
        == (
            second["gitCommit"],
            second["gitStatusHash"],
        ),
    }
    passed = (
        first["status"] == second["status"] == "success"
        and first["trustStatus"] == second["trustStatus"] == "trusted"
        and bool(first["datasetReleaseId"])
        and bool(second["datasetReleaseId"])
        and bool(first["reproducibilityCertificateId"])
        and bool(second["reproducibilityCertificateId"])
        and bool(first["validationPassed"])
        and bool(second["validationPassed"])
        and bool(first["canonicalRecomputePassed"])
        and bool(second["canonicalRecomputePassed"])
        and all(comparisons.values())
    )
    return {
        "schemaVersion": 1,
        "generatedAt": _utc_now(),
        "passed": passed,
        "payload": GOLDEN_PAYLOAD,
        "runs": [first, second],
        "comparisons": comparisons,
        "rawDigestExpectedToDiffer": True,
        "rawDigestDiffered": first["rawResultSha256"] != second["rawResultSha256"],
    }


def _write_evidence(output_dir: Path, report: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "release-trust-evidence.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    checksum_paths = [
        path
        for path in (
            output_dir / "archive-reconciliation.json",
            report_path,
        )
        if path.is_file()
    ]
    checksums = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}"
        for path in checksum_paths
    ]
    (output_dir / "SHA256SUMS").write_text("\n".join(checksums) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the P0 trust/data-coverage release acceptance against production data."
    )
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--project-id",
        help="Existing project for the Golden Pair; defaults to the newest validated project.",
    )
    parser.add_argument(
        "--first-run-id",
        help="Resume an already-created first Golden run instead of creating a duplicate.",
    )
    parser.add_argument(
        "--second-run-id",
        help="Reuse an already-created second Golden run instead of creating a duplicate.",
    )
    parser.add_argument(
        "--run-id",
        default="b15c8791-1e35-499d-9730-6b4d4e42164b",
        help="Successful ten-dataset production sync run.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "audit-output" / f"p0-trust-{RELEASE_DATE}"),
    )
    args = parser.parse_args()
    GOLDEN_PAYLOAD["projectId"] = _resolve_golden_project_id(args.project_id)

    sections = {
        "sourceQaReferenceMatrix": source_qa_reference_matrix(),
        "csi300": csi300_evidence(),
        "archives": archive_evidence(args.run_id),
        "releaseGoldens": golden_evidence(
            args.api_url,
            args.first_run_id,
            args.second_run_id,
        ),
    }
    report = {
        "schemaVersion": 1,
        "releaseDate": RELEASE_DATE,
        "generatedAt": _utc_now(),
        "passed": all(section.get("passed") for section in sections.values()),
        **sections,
    }
    _write_evidence(Path(args.output_dir), report)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
