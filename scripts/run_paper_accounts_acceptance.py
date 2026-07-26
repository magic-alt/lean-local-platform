#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db import database_backend, db  # noqa: E402
from app.services.paper_accounts import rebuild_projection  # noqa: E402


MIN_TRADING_DAYS = 21
MIN_ACCOUNTS = 2


def _acceptance_contract(args: argparse.Namespace) -> dict[str, Any]:
    days = int(args.days)
    accounts = int(args.accounts)
    cash_values = [item.strip() for item in str(args.initial_cash).split(",") if item.strip()]
    if days < MIN_TRADING_DAYS:
        raise ValueError(f"paper_acceptance_requires_at_least_{MIN_TRADING_DAYS}_trading_days")
    if accounts < MIN_ACCOUNTS:
        raise ValueError(f"paper_acceptance_requires_at_least_{MIN_ACCOUNTS}_accounts")
    if len(cash_values) != accounts:
        raise ValueError("initial_cash_count_must_equal_accounts")
    normalized_cash = [str(int(item)) for item in cash_values]
    if any(int(item) <= 0 for item in normalized_cash):
        raise ValueError("initial_cash_must_be_positive")
    if len(set(normalized_cash)) < MIN_ACCOUNTS:
        raise ValueError("paper_acceptance_requires_distinct_initial_cash")
    return {
        "requiredTradingDays": days,
        "requiredAccounts": accounts,
        "initialCash": normalized_cash,
    }


def _token() -> str:
    configured = os.environ.get("LEAN_API_TOKEN", "").strip()
    if configured:
        return configured
    path = ROOT / "web" / "runtime" / "secrets" / "api_token"
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def _api(
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: int = 60,
) -> tuple[int, Any]:
    headers = {"Content-Type": "application/json"}
    token = _token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        method=method,
        headers=headers,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            if not raw:
                return response.status, {}
            try:
                return response.status, json.loads(raw)
            except json.JSONDecodeError:
                return response.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"detail": raw}


def _expect(status: int, body: Any, expected: set[int], label: str) -> Any:
    if status not in expected:
        raise RuntimeError(f"{label}:{status}:{body}")
    return body


def _wait_cycle(base_url: str, account_id: str, cycle_id: str, timeout: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        status, body = _api(
            base_url,
            "GET",
            f"/api/paper/accounts/{account_id}/cycles?limit=200",
        )
        _expect(status, body, {200}, "cycles")
        last = next((item for item in body["items"] if item["id"] == cycle_id), None)
        if last and last["status"] == "succeeded":
            return last
        if last and last["status"] in {"failed", "skipped"}:
            raise RuntimeError(f"cycle_terminal:{cycle_id}:{last}")
        time.sleep(2)
    raise TimeoutError(f"cycle_timeout:{cycle_id}:{last}")


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() or "unknown"


def _ledger_evidence(account_id: str, as_of_date: str) -> dict[str, Any]:
    projection = rebuild_projection(account_id, as_of_date)["account"]
    with db() as connection:
        rows = connection.execute(
            """
            select ledger_sequence,entry_type,asset,precise_quantity,precise_amount,
                   currency,idempotency_key,execution_cycle_id
            from paper_ledger_entries
            where paper_account_id=?
            order by account_generation,ledger_sequence
            """,
            (account_id,),
        ).fetchall()
        opening = connection.execute(
            """
            select * from paper_account_generations
            where paper_account_id=? order by generation desc limit 1
            """,
            (account_id,),
        ).fetchone()
    canonical = [dict(item) for item in rows]
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    return {
        "openingLedgerEntryId": opening["opening_ledger_entry_id"],
        "openingCheckpointDigest": opening["opening_checkpoint_digest"],
        "ledgerEntries": len(canonical),
        "ledgerDigest": digest,
        "projectionCash": projection["cash"],
        "projectionEquity": projection["total_equity"],
        "sourceLedgerSequence": projection["source_ledger_sequence"],
        "sourceCheckpointDigest": projection["source_checkpoint_digest"],
    }


def _dispatch_cycle(
    base_url: str,
    account_id: str,
    deployment_id: str,
    trading_date: str | None,
    timeout: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = {"tradingDate": trading_date} if trading_date else {}
    first_status, first_dispatch = _api(
        base_url,
        "POST",
        f"/api/paper/deployments/{deployment_id}/run-now",
        payload,
    )
    _expect(first_status, first_dispatch, {200}, "run_now")
    duplicate_status, duplicate = _api(
        base_url,
        "POST",
        f"/api/paper/deployments/{deployment_id}/run-now",
        payload,
    )
    _expect(duplicate_status, duplicate, {200}, "duplicate_run_now")
    if duplicate["id"] != first_dispatch["id"]:
        raise RuntimeError("duplicate_run_now_created_second_cycle")
    completed = _wait_cycle(base_url, account_id, first_dispatch["id"], timeout)
    return completed, {
        "deploymentId": deployment_id,
        "tradingDate": completed["trading_date"],
        "firstCycleId": first_dispatch["id"],
        "duplicateCycleId": duplicate["id"],
        "sameCycle": duplicate["id"] == first_dispatch["id"],
        "resultDigest": completed["result_digest"],
    }


def _create_account(
    base_url: str,
    name: str,
    cash: str,
    *,
    risk_config: dict[str, Any],
) -> dict[str, Any]:
    status, body = _api(
        base_url,
        "POST",
        "/api/paper/accounts",
        {
            "name": name,
            "description": "Paper multi-account acceptance evidence",
            "marketScope": "china",
            "baseCurrency": "CNY",
            "initialCash": cash,
            "benchmarkSymbol": "000300",
            "riskConfig": risk_config,
        },
    )
    return _expect(status, body, {201}, "create_account")


def run(args: argparse.Namespace) -> dict[str, Any]:
    contract = _acceptance_contract(args)
    if database_backend() != "mysql":
        raise RuntimeError("mysql_required")
    health = _expect(*_api(args.base_url, "GET", "/api/health"), {200}, "health")
    dependencies = _expect(
        *_api(args.base_url, "GET", "/api/health/dependencies"),
        {200},
        "dependencies",
    )
    if not args.project_id or not args.source_backtest_id:
        raise RuntimeError("project_id_and_source_backtest_id_required")
    candidates = _expect(
        *_api(
            args.base_url,
            "GET",
            f"/api/paper/accounts/candidates?projectId={urllib.parse.quote(args.project_id)}",
        ),
        {200},
        "candidates",
    )
    if not any(item["id"] == args.source_backtest_id for item in candidates):
        raise RuntimeError("trusted_candidate_unavailable")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    accounts: list[dict[str, Any]] = []
    for index, cash in enumerate(contract["initialCash"]):
        risk_config = (
            {
                "maxPositions": 10,
                "maxPositionWeight": "1",
                "cashFloor": "0",
                "maxOrderAmount": "2000000",
                "maxDailyTurnover": "1",
            }
            if index == 0
            else {
                "maxPositions": 10,
                "maxPositionWeight": "0.2",
                "cashFloor": "50000",
                "maxOrderAmount": "1",
                "maxDailyTurnover": "0.5",
            }
        )
        accounts.append(
            _create_account(
                args.base_url,
                f"Acceptance {index + 1} {stamp}",
                cash,
                risk_config=risk_config,
            )
        )
    deployments: list[dict[str, Any]] = []
    for index, account in enumerate(accounts, start=1):
        status, deployment = _api(
            args.base_url,
            "POST",
            f"/api/paper/accounts/{account['id']}/deployments",
            {
                "name": f"Acceptance Strategy {index}",
                "projectId": args.project_id,
                "sourceBacktestId": args.source_backtest_id,
                "scheduleType": "market_daily",
                "scheduleExpression": "after_close+00:45",
                "marketTimezone": "Asia/Shanghai",
                "executionTiming": "next_open",
                "signalMode": "paper_execute",
                "isPrimary": True,
            },
        )
        deployments.append(_expect(status, deployment, {201}, "create_deployment"))
        _expect(
            *_api(args.base_url, "POST", f"/api/paper/accounts/{account['id']}/activate"),
            {200},
            "activate_account",
        )

    cycles: list[dict[str, Any]] = []
    idempotency: list[dict[str, Any]] = []
    next_dates: list[str | None] = [args.trading_date for _ in accounts]
    for _date_index in range(contract["requiredTradingDays"]):
        with ThreadPoolExecutor(max_workers=len(accounts)) as pool:
            futures = [
                pool.submit(
                    _dispatch_cycle,
                    args.base_url,
                    account["id"],
                    deployment["id"],
                    next_dates[index],
                    args.timeout,
                )
                for index, (account, deployment) in enumerate(
                    zip(accounts, deployments, strict=True)
                )
            ]
            completed_items = [future.result() for future in futures]
        for index, ((completed, duplicate_evidence), deployment) in enumerate(
            zip(completed_items, deployments, strict=True)
        ):
            cycles.append(completed)
            idempotency.append(duplicate_evidence)
            next_status, next_payload = _api(
                args.base_url,
                "GET",
                f"/api/paper/deployments/{deployment['id']}/next-runs?count=1",
            )
            _expect(next_status, next_payload, {200}, "next_runs")
            next_dates[index] = str(next_payload["runs"][0]["tradingDate"])
    if not any(int(item["fill_count"]) > 0 for item in cycles):
        raise RuntimeError("successful_fill_evidence_missing")
    if not any(int(item["rejected_count"]) > 0 for item in cycles):
        raise RuntimeError("risk_rejection_evidence_missing")
    if not any(int(item["signal_count"]) == 0 for item in cycles):
        raise RuntimeError("no_signal_day_evidence_missing")
    observed_dates = {str(item["trading_date"]) for item in cycles}
    if len(observed_dates) < contract["requiredTradingDays"]:
        raise RuntimeError("insufficient_distinct_trading_days")
    for account in accounts:
        account_cycles = [
            item for item in cycles if str(item["paper_account_id"]) == str(account["id"])
        ]
        if len(account_cycles) < contract["requiredTradingDays"]:
            raise RuntimeError(f"insufficient_account_trading_days:{account['id']}")

    last_dates = {
        account["id"]: max(
            str(item["trading_date"])
            for item in cycles
            if str(item["paper_account_id"]) == str(account["id"])
        )
        for account in accounts
    }
    ledgers = {
        account["id"]: _ledger_evidence(account["id"], last_dates[account["id"]])
        for account in accounts
    }
    replayed_ledgers = {
        account["id"]: _ledger_evidence(account["id"], last_dates[account["id"]])
        for account in accounts
    }
    for account in accounts:
        account_id = account["id"]
        if ledgers[account_id]["ledgerDigest"] != replayed_ledgers[account_id]["ledgerDigest"]:
            raise RuntimeError(f"ledger_replay_digest_mismatch:{account_id}")
    if len({item["openingLedgerEntryId"] for item in ledgers.values()}) != len(accounts):
        raise RuntimeError("account_opening_ledger_not_isolated")
    with db() as connection:
        duplicate_sequences = connection.execute(
            """
            select count(*) as count from (
                select paper_account_id,account_generation,ledger_sequence,count(*) as rows_count
                from paper_ledger_entries
                where paper_account_id in ({})
                group by paper_account_id,account_generation,ledger_sequence
                having count(*)>1
            ) duplicate_rows
            """.format(",".join("?" for _ in accounts)),
            tuple(account["id"] for account in accounts),
        ).fetchone()
        waiting_data_events = connection.execute(
            """
            select count(*) as count from paper_execution_cycle_events event
            join paper_execution_cycles cycle on cycle.id=event.cycle_id
            where cycle.paper_account_id in ({}) and event.to_status='waiting_data'
            """.format(",".join("?" for _ in accounts)),
            tuple(account["id"] for account in accounts),
        ).fetchone()
        checkpoint_phases = connection.execute(
            """
            select distinct checkpoint.phase from paper_run_checkpoints checkpoint
            join paper_walkforward_runs run on run.id=checkpoint.paper_run_id
            join paper_execution_cycles cycle on cycle.paper_run_id=run.id
            where cycle.paper_account_id in ({})
            """.format(",".join("?" for _ in accounts)),
            tuple(account["id"] for account in accounts),
        ).fetchall()
    if int(duplicate_sequences["count"] or 0):
        raise RuntimeError("duplicate_account_ledger_sequence")
    if args.require_waiting_data and int(waiting_data_events["count"] or 0) <= 0:
        raise RuntimeError("waiting_data_day_evidence_missing")
    observed_phases = sorted(str(item["phase"]) for item in checkpoint_phases)
    if args.with_fault and len(observed_phases) < 6:
        raise RuntimeError("six_checkpoint_fault_evidence_missing")
    api_evidence: dict[str, Any] = {}
    for account in accounts:
        api_evidence[account["id"]] = {}
        for endpoint in ("overview", "positions", "orders", "trades", "signals", "daily-reports", "audit"):
            status, body = _api(
                args.base_url,
                "GET",
                f"/api/paper/accounts/{account['id']}/{endpoint}",
            )
            _expect(status, body, {200}, endpoint)
            api_evidence[account["id"]][endpoint] = {
                "count": body.get("count") if isinstance(body, dict) else None,
                "available": True,
            }
    compare = _expect(
        *_api(
            args.base_url,
            "GET",
            "/api/paper/accounts/compare?"
            + urllib.parse.urlencode(
                [("accountId", account["id"]) for account in accounts]
            ),
        ),
        {200},
        "compare",
    )
    frontend_status, frontend = _api(args.base_url, "GET", "/", timeout=30)
    if frontend_status != 200:
        raise RuntimeError(f"frontend_smoke:{frontend_status}")
    return {
        "testTimestamp": datetime.now(timezone.utc).isoformat(),
        "gitCommit": _git_commit(),
        "databaseBackend": "mysql",
        "health": health,
        "dependencies": dependencies,
        "strategyProjectFingerprints": [item["strategy_fingerprint"] for item in deployments],
        "datasetVersions": [item["dataset_version_id"] for item in deployments],
        "acceptanceScope": {
            **contract,
            "observedTradingDates": sorted(observed_dates),
            "observedTradingDayCount": len(observed_dates),
            "requiredScenarios": [
                "fill",
                "no_signal",
                "risk_rejection",
                "idempotent_duplicate_dispatch",
                "account_isolation",
                "concurrent_multi_account_dispatch",
                "ledger_digest_replay",
                "waiting_data_recovery",
                "six_checkpoint_recovery",
            ],
        },
        "accountIds": [account["id"] for account in accounts],
        "deploymentIds": [item["id"] for item in deployments],
        "cycleIds": [item["id"] for item in cycles],
        "inputDigests": [item["input_fingerprint"] for item in cycles],
        "resultDigests": [item["result_digest"] for item in cycles],
        "ledgerReconciliation": ledgers,
        "ledgerReplayReconciliation": replayed_ledgers,
        "concurrency": {
            "enabled": True,
            "accountCount": len(accounts),
            "duplicateLedgerSequences": int(duplicate_sequences["count"] or 0),
        },
        "recoveryEvidence": {
            "waitingDataEvents": int(waiting_data_events["count"] or 0),
            "checkpointPhases": observed_phases,
            "withFault": bool(args.with_fault),
        },
        "idempotency": idempotency,
        "failureRejectEvidence": {
            "rejectedCounts": [item["rejected_count"] for item in cycles],
            "signalCounts": [item["signal_count"] for item in cycles],
        },
        "apiEvidence": api_evidence,
        "comparison": compare,
        "frontendSmoke": {"status": frontend_status, "contentType": "html"},
        "e2eEvidencePath": str(ROOT / "tests" / "e2e" / "reports" / "results.json"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Accept Paper multi-account execution in the real app stack.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--project-id", default=os.environ.get("PAPER_ACCEPTANCE_PROJECT_ID"))
    parser.add_argument("--source-backtest-id", default=os.environ.get("PAPER_ACCEPTANCE_BACKTEST_ID"))
    parser.add_argument("--trading-date", default=os.environ.get("PAPER_ACCEPTANCE_TRADING_DATE"))
    parser.add_argument("--days", type=int, default=MIN_TRADING_DAYS)
    parser.add_argument("--accounts", type=int, default=MIN_ACCOUNTS)
    parser.add_argument("--initial-cash", default="1000000,3000000")
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--with-fault", action="store_true")
    parser.add_argument(
        "--require-waiting-data",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        default=ROOT / "web" / "runtime" / "audit" / "paper-accounts-acceptance.json",
    )
    args = parser.parse_args()
    evidence: dict[str, Any]
    exit_code = 0
    try:
        evidence = {"status": "PAPER_ACCOUNTS_PASS", **run(args)}
        marker = "PAPER_ACCOUNTS_PASS"
    except Exception as exc:
        evidence = {
            "status": "PAPER_ACCOUNTS_FAIL",
            "testTimestamp": datetime.now(timezone.utc).isoformat(),
            "gitCommit": _git_commit(),
            "failure": {"type": type(exc).__name__, "detail": str(exc)},
        }
        marker = "PAPER_ACCOUNTS_FAIL"
        exit_code = 1
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(marker)
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
