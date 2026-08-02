from __future__ import annotations

from typing import Any

from ..db import db, row_to_dict, rows_to_dicts, utc_now


def _final_gate_passed(validation: dict[str, Any]) -> bool:
    if validation.get("passed") is not True:
        return False
    return not any(
        gate.get("passed") is not True
        and str(gate.get("severity") or "").lower() == "critical"
        for gate in validation.get("gates") or []
        if isinstance(gate, dict)
    )


def trust_decision(run: dict[str, Any]) -> tuple[str, str | None]:
    validation = dict(run.get("validation") or {})
    if run.get("status") != "success":
        return "invalid", f"terminal_status_{run.get('status') or 'unknown'}"
    if not _final_gate_passed(validation):
        return "invalid", "final_validation_not_passed"
    release_id = str(run.get("dataset_release_id") or "")
    certificate_id = str(run.get("reproducibility_certificate_id") or "")
    if not release_id:
        return "legacy_unverified", "dataset_release_missing"
    if not certificate_id:
        return "unverified", "reproducibility_certificate_missing"
    fingerprint_release = str((run.get("fingerprint") or {}).get("datasetReleaseId") or "")
    if fingerprint_release != release_id:
        return "invalid", "dataset_release_changed_during_run"
    with db() as connection:
        release = connection.execute(
            """
            select status,is_production,is_certified from dataset_releases where id=?
            """,
            (release_id,),
        ).fetchone()
        certificate = connection.execute(
            """
            select status,dataset_release_id from reproducibility_certificates
            where id=? and run_id=?
            """,
            (certificate_id, run["id"]),
        ).fetchone()
    if not release or release["status"] != "active" or not release["is_production"] or not release["is_certified"]:
        return "invalid", "dataset_release_not_active_certified"
    if not certificate or certificate["status"] != "valid" or certificate["dataset_release_id"] != release_id:
        return "invalid", "reproducibility_certificate_invalid"
    return "trusted", None


def reconcile_backtest_trust(run_id: str | None = None) -> dict[str, Any]:
    clauses = " where id=?" if run_id else ""
    values: tuple[Any, ...] = (run_id,) if run_id else ()
    with db() as connection:
        rows = rows_to_dicts(connection.execute(f"select * from backtest_runs{clauses}", values).fetchall())
    counts: dict[str, int] = {}
    decisions = []
    for run in rows:
        status, reason = trust_decision(run)
        with db() as connection:
            connection.execute(
                """
                update backtest_runs
                set trust_status=?,trust_reason=?,trust_evaluated_at=?
                where id=?
                """,
                (status, reason, utc_now(), run["id"]),
            )
        counts[status] = counts.get(status, 0) + 1
        decisions.append({"runId": run["id"], "trustStatus": status, "trustReason": reason})
    return {"count": len(decisions), "counts": counts, "items": decisions}


def get_backtest_trust(run_id: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute(
            """
            select id,trust_status,trust_reason,trust_evaluated_at
            from backtest_runs where id=?
            """,
            (run_id,),
        ).fetchone()
    return row_to_dict(row)
