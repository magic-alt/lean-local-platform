from __future__ import annotations

import hashlib
import json
import uuid
from decimal import Decimal
from typing import Any

from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _member_snapshot(connection: Any, account_id: str) -> dict[str, Any]:
    account = connection.execute(
        "select * from paper_accounts where id=?",
        (account_id,),
    ).fetchone()
    if not account:
        raise ValueError(f"Paper account not found: {account_id}")
    deployment = connection.execute(
        """
        select * from paper_strategy_deployments
        where paper_account_id=? and is_primary=1
        order by version desc,created_at desc limit 1
        """,
        (account_id,),
    ).fetchone()
    return {
        "account": row_to_dict(account) or {},
        "deployment": row_to_dict(deployment),
    }


def create_cohort(
    *,
    name: str,
    account_ids: list[str],
    required_sessions: int = 21,
) -> dict[str, Any]:
    normalized_ids = list(dict.fromkeys(str(item).strip() for item in account_ids if str(item).strip()))
    if len(normalized_ids) < 2:
        raise ValueError("Paper certification requires at least two distinct accounts.")
    if int(required_sessions) < 21:
        raise ValueError("Paper certification requires at least 21 sessions per account.")
    cohort_id = str(uuid.uuid4())
    now = utc_now()
    with db() as connection:
        snapshots = [_member_snapshot(connection, account_id) for account_id in normalized_ids]
        opening_cash = {Decimal(str(item["account"]["initial_cash"])) for item in snapshots}
        if len(opening_cash) != len(snapshots):
            raise ValueError("Certification accounts must have distinct opening balances.")
        contract = {
            "requiredAccounts": len(snapshots),
            "requiredSessions": int(required_sessions),
            "accountIsolation": True,
            "immutableLedger": True,
            "cycleIdempotency": True,
            "projectionReplay": True,
        }
        connection.execute(
            """
            insert into paper_certification_cohorts
                (id,name,status,required_accounts,required_sessions,contract_json,created_at)
            values (?,?, 'collecting', ?,?,?,?)
            """,
            (cohort_id, name.strip() or "Paper certification cohort", len(snapshots), int(required_sessions), json_dump(contract), now),
        )
        for snapshot in snapshots:
            account = snapshot["account"]
            deployment = snapshot["deployment"] or {}
            connection.execute(
                """
                insert into paper_certification_members
                    (id,cohort_id,paper_account_id,account_generation,opening_cash,
                     risk_profile_id,deployment_id,strategy_fingerprint,dataset_fingerprint,
                     execution_mode,status,added_at)
                values (?,?,?,?,?,?,?,?,?,?,'collecting',?)
                """,
                (
                    str(uuid.uuid4()),
                    cohort_id,
                    account["id"],
                    account["current_generation"],
                    account["initial_cash"],
                    account.get("active_risk_profile_id"),
                    deployment.get("id"),
                    deployment.get("strategy_fingerprint"),
                    deployment.get("dataset_fingerprint"),
                    account["execution_mode"],
                    now,
                ),
            )
    return refresh_cohort(cohort_id)


def rebind_collecting_cohort_members(
    cohort_id: str,
    deployment_ids: dict[str, str],
) -> dict[str, Any]:
    """Rebind an empty collecting cohort to explicit replacement deployments.

    Cohort evidence becomes immutable as soon as any member has certified
    sessions or the cohort leaves ``collecting``.  Before that point a source
    admission fix may legitimately replace a deployment; requiring explicit
    account-to-deployment IDs keeps that repair auditable and prevents an
    implicit switch to whichever deployment happens to be newest.
    """
    now = utc_now()
    with db() as connection:
        cohort = row_to_dict(
            connection.execute(
                "select * from paper_certification_cohorts where id=?",
                (cohort_id,),
            ).fetchone()
        )
        if not cohort:
            raise KeyError("Paper certification cohort not found.")
        if cohort["status"] != "collecting":
            raise ValueError("Certified or invalid cohort bindings are immutable.")
        members = rows_to_dicts(
            connection.execute(
                "select * from paper_certification_members where cohort_id=?",
                (cohort_id,),
            ).fetchall()
        )
        expected_accounts = {str(member["paper_account_id"]) for member in members}
        if set(deployment_ids) != expected_accounts:
            raise ValueError("Deployment bindings must cover every cohort member exactly once.")
        if any(
            member["status"] != "collecting" or int(member.get("certified_sessions") or 0) != 0
            for member in members
        ):
            raise ValueError("Cohort bindings are immutable after session evidence is certified.")
        for member in members:
            account_id = str(member["paper_account_id"])
            deployment = row_to_dict(
                connection.execute(
                    """
                    select * from paper_strategy_deployments
                    where id=? and paper_account_id=? and is_primary=1
                    """,
                    (deployment_ids[account_id], account_id),
                ).fetchone()
            )
            if not deployment or deployment["status"] not in {"active", "paused", "error"}:
                raise ValueError(f"Current primary deployment is unavailable for account {account_id}.")
            connection.execute(
                """
                update paper_certification_members
                set deployment_id=?,strategy_fingerprint=?,dataset_fingerprint=?,
                    status='collecting',certified_sessions=0,evidence_json=null,
                    evidence_digest=null,refreshed_at=?
                where id=?
                """,
                (
                    deployment["id"],
                    deployment["strategy_fingerprint"],
                    deployment["dataset_fingerprint"],
                    now,
                    member["id"],
                ),
            )
        connection.execute(
            """
            update paper_certification_cohorts
            set evidence_digest=null,refreshed_at=? where id=?
            """,
            (now, cohort_id),
        )
    return get_cohort(cohort_id)


def _refresh_member(connection: Any, member: dict[str, Any], required_sessions: int, now: str) -> dict[str, Any]:
    account = connection.execute(
        "select * from paper_accounts where id=?",
        (member["paper_account_id"],),
    ).fetchone()
    deployment = None
    if member.get("deployment_id"):
        deployment = connection.execute(
            "select * from paper_strategy_deployments where id=?",
            (member["deployment_id"],),
        ).fetchone()
    report_rows = connection.execute(
        """
        select report.trading_date,report.result_digest,cycle.status,
               cycle.account_checkpoint_digest,cycle.input_fingerprint
        from paper_account_daily_reports report
        join paper_execution_cycles cycle on cycle.id=report.cycle_id
        where report.paper_account_id=?
          and cycle.account_generation=?
          and report.deployment_id=?
          and cycle.status in ('succeeded','skipped')
        order by report.trading_date
        """,
        (member["paper_account_id"], member["account_generation"], member.get("deployment_id")),
    ).fetchall()
    dates = list(dict.fromkeys(str(row["trading_date"]) for row in report_rows))
    checks = {
        "accountExists": account is not None,
        "generationFrozen": bool(account and int(account["current_generation"]) == int(member["account_generation"])),
        "openingBalanceFrozen": bool(account and Decimal(str(account["initial_cash"])) == Decimal(str(member["opening_cash"]))),
        "riskProfileFrozen": bool(account and account["active_risk_profile_id"] == member.get("risk_profile_id")),
        "deploymentExists": deployment is not None,
        "strategyFingerprintFrozen": bool(
            deployment and deployment["strategy_fingerprint"] == member.get("strategy_fingerprint")
        ),
        "datasetFingerprintFrozen": bool(
            deployment and deployment["dataset_fingerprint"] == member.get("dataset_fingerprint")
        ),
        "sessionEvidenceComplete": len(dates) >= required_sessions,
        "reportDigestsPresent": all(bool(row["result_digest"]) for row in report_rows),
        "checkpointDigestsPresent": all(bool(row["account_checkpoint_digest"]) for row in report_rows),
    }
    status = "certified" if all(checks.values()) else "invalid" if member.get("status") == "certified" else "collecting"
    evidence = {
        "paperAccountId": member["paper_account_id"],
        "accountGeneration": member["account_generation"],
        "certifiedSessions": len(dates),
        "requiredSessions": required_sessions,
        "firstTradingDate": dates[0] if dates else None,
        "lastTradingDate": dates[-1] if dates else None,
        "checks": checks,
        "sessionDigests": [
            {
                "tradingDate": row["trading_date"],
                "resultDigest": row["result_digest"],
                "checkpointDigest": row["account_checkpoint_digest"],
                "inputFingerprint": row["input_fingerprint"],
            }
            for row in report_rows
        ],
    }
    evidence_digest = _digest(evidence)
    connection.execute(
        """
        update paper_certification_members
        set status=?,certified_sessions=?,evidence_json=?,evidence_digest=?,refreshed_at=?
        where id=?
        """,
        (status, len(dates), json_dump(evidence), evidence_digest, now, member["id"]),
    )
    return {**member, "status": status, "certified_sessions": len(dates), "evidence": evidence, "evidence_digest": evidence_digest}


def refresh_cohort(cohort_id: str) -> dict[str, Any]:
    now = utc_now()
    with db() as connection:
        cohort = row_to_dict(
            connection.execute("select * from paper_certification_cohorts where id=?", (cohort_id,)).fetchone()
        )
        if not cohort:
            raise KeyError("Paper certification cohort not found.")
        members = rows_to_dicts(
            connection.execute(
                "select * from paper_certification_members where cohort_id=? order by added_at,paper_account_id",
                (cohort_id,),
            ).fetchall()
        )
        refreshed = [
            _refresh_member(connection, member, int(cohort["required_sessions"]), now)
            for member in members
        ]
        distinct_cash = len({Decimal(str(member["opening_cash"])) for member in refreshed}) == len(refreshed)
        certified = (
            len(refreshed) >= int(cohort["required_accounts"])
            and distinct_cash
            and all(member["status"] == "certified" for member in refreshed)
        )
        status = "certified" if certified else "invalid" if cohort["status"] == "certified" else "collecting"
        evidence = {
            "cohortId": cohort_id,
            "requiredAccounts": cohort["required_accounts"],
            "requiredSessions": cohort["required_sessions"],
            "distinctOpeningBalances": distinct_cash,
            "members": [
                {
                    "paperAccountId": member["paper_account_id"],
                    "status": member["status"],
                    "certifiedSessions": member["certified_sessions"],
                    "evidenceDigest": member["evidence_digest"],
                }
                for member in refreshed
            ],
        }
        digest = _digest(evidence)
        connection.execute(
            """
            update paper_certification_cohorts
            set status=?,evidence_digest=?,refreshed_at=?,
                certified_at=case when ?='certified' then coalesce(certified_at,?) else certified_at end
            where id=?
            """,
            (status, digest, now, status, now, cohort_id),
        )
    return get_cohort(cohort_id)


def get_cohort(cohort_id: str) -> dict[str, Any]:
    with db() as connection:
        cohort = row_to_dict(
            connection.execute("select * from paper_certification_cohorts where id=?", (cohort_id,)).fetchone()
        )
        if not cohort:
            raise KeyError("Paper certification cohort not found.")
        cohort["members"] = rows_to_dicts(
            connection.execute(
                "select * from paper_certification_members where cohort_id=? order by added_at,paper_account_id",
                (cohort_id,),
            ).fetchall()
        )
    return cohort


def list_cohorts() -> dict[str, Any]:
    with db() as connection:
        rows = rows_to_dicts(
            connection.execute("select * from paper_certification_cohorts order by created_at desc").fetchall()
        )
    return {"items": rows, "count": len(rows)}
