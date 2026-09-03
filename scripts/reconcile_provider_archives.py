#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db import db, json_dump, row_to_dict, rows_to_dicts, utc_now  # noqa: E402
from app.services.data_sync import BULK_DATASET_KEYS, _sync_completion_evidence  # noqa: E402
from app.services.db_object_store import integrity_report  # noqa: E402


def _latest_bulk_dataset_run() -> dict[str, Any]:
    required = set(BULK_DATASET_KEYS)
    with db() as connection:
        rows = connection.execute(
            """
            select *
            from data_sync_runs
            where status='success'
            order by created_at desc
            """
        ).fetchall()
    for raw in rows:
        run = row_to_dict(raw) or {}
        requested = set(run.get("requested_datasets") or [])
        summary = run.get("summary") or {}
        evidence = summary.get("completionEvidence") or {}
        evidence_keys = {str(item.get("datasetKey")) for item in evidence.get("items") or []}
        if required <= (requested | evidence_keys) and evidence.get("passed"):
            return run
    raise RuntimeError(
        "No successful bulk sync run covering all "
        f"{len(required)} managed datasets with passing completion evidence was found."
    )


# Compatibility alias for callers that imported the historical name before the
# managed bulk set grew beyond ten datasets.
_latest_ten_dataset_run = _latest_bulk_dataset_run


def reconcile(*, apply: bool = False, run_id: str | None = None) -> dict[str, Any]:
    run = _latest_bulk_dataset_run()
    if run_id and run["id"] != run_id:
        with db() as connection:
            selected = row_to_dict(
                connection.execute(
                    "select * from data_sync_runs where id=? and status='success'",
                    (run_id,),
                ).fetchone()
            )
        if not selected:
            raise RuntimeError(f"Successful sync run not found: {run_id}")
        run = selected
    evidence = _sync_completion_evidence(str(run["id"]), set(BULK_DATASET_KEYS))
    evidence_by_key = {str(item["datasetKey"]): item for item in evidence["items"]}
    object_integrity = integrity_report()
    with db() as connection:
        issues = rows_to_dicts(
            connection.execute(
                """
                select *
                from provider_raw_archive_issues
                where coalesce(status,'open')='open'
                order by dataset_key,archive_created_at,archive_id
                """
            ).fetchall()
        )
        active_ids = {
            str(row["id"])
            for row in connection.execute(
                "select id from provider_raw_archives"
            ).fetchall()
        }

    decisions: list[dict[str, Any]] = []
    updates: list[tuple[Any, ...]] = []
    resolved_at = utc_now()
    for issue in issues:
        dataset_key = str(issue["dataset_key"])
        item = evidence_by_key.get(dataset_key)
        reasons = []
        if str(issue["archive_id"]) in active_ids:
            reasons.append("quarantined_issue_still_has_active_reference")
        if not object_integrity.get("passed"):
            reasons.append("active_object_integrity_failed")
        if not item or not item.get("passed"):
            reasons.append("replacement_dataset_evidence_failed")
        passed = not reasons
        resolution_code = None
        if passed:
            resolution_code = (
                "replaced_by_verified_archive"
                if item.get("archiveRequired")
                else "superseded_by_lossless_canonical_evidence"
            )
            resolution_evidence = {
                "schemaVersion": 1,
                "runId": run["id"],
                "datasetEvidence": item,
                "activeObjectIntegrity": object_integrity,
                "historicalObjectRecovered": False,
                "historicalReferenceRetainedInIssueLedger": True,
            }
            updates.append(
                (
                    "superseded_verified",
                    resolution_code,
                    run["id"],
                    json_dump(resolution_evidence),
                    resolved_at,
                    issue["archive_id"],
                )
            )
        decisions.append(
            {
                "archiveId": issue["archive_id"],
                "datasetKey": dataset_key,
                "passed": passed,
                "resolutionCode": resolution_code,
                "reasons": reasons,
            }
        )

    if apply and updates:
        with db() as connection:
            connection.executemany(
                """
                update provider_raw_archive_issues
                set status=?,resolution_code=?,resolution_run_id=?,
                    resolution_evidence_json=?,resolved_at=?
                where archive_id=? and coalesce(status,'open')='open'
                """,
                updates,
            )

    passed = bool(
        evidence.get("passed")
        and object_integrity.get("passed")
        and all(item["passed"] for item in decisions)
    )
    return {
        "schemaVersion": 2,
        "generatedAt": resolved_at,
        "mode": "apply" if apply else "dry_run",
        "passed": passed,
        "runId": run["id"],
        "bulkDatasetCount": len(BULK_DATASET_KEYS),
        "bulkDatasetEvidence": evidence,
        # Temporary compatibility alias for scripts consuming schema v1 output.
        "tenDatasetEvidence": evidence,
        "activeObjectIntegrity": object_integrity,
        "openIssueCount": len(issues),
        "reconciledCount": len(updates),
        "remainingOpenCount": sum(1 for item in decisions if not item["passed"]),
        "decisions": decisions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Reconcile quarantined provider archive references against the current "
            "verified managed bulk dataset set."
        )
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--run-id")
    parser.add_argument("--output")
    args = parser.parse_args()
    report = reconcile(apply=args.apply, run_id=args.run_id)
    encoded = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
