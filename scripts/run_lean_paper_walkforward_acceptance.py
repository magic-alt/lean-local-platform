#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.ashare_repository import trade_dates_between  # noqa: E402


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
    try:
        return token_path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _api(
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: int = 60,
) -> tuple[int, Any]:
    headers = {"Content-Type": "application/json"}
    token = _api_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=(json.dumps(payload).encode("utf-8") if payload is not None else None),
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            body: Any = json.loads(raw)
        except json.JSONDecodeError:
            body = {"detail": raw}
        return exc.code, body


def _field(item: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in item:
            return item[name]
    return None


def _run_for_date(items: list[dict[str, Any]], trade_date: str) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in items
            if str(_field(item, "trade_date", "tradeDate") or "") == trade_date
        ),
        None,
    )


def _wait_for_run(
    base_url: str,
    session_id: str,
    trade_date: str,
    *,
    timeout_seconds: int,
    poll_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        status, body = _api(base_url, "GET", f"/api/paper/{session_id}/runs")
        if status >= 400:
            raise RuntimeError(f"paper_runs_unavailable:{status}:{body}")
        items = body if isinstance(body, list) else list(body.get("items") or [])
        last = _run_for_date(items, trade_date)
        run_status = str((last or {}).get("status") or "")
        if run_status == "success":
            return last or {}
        if run_status == "failed":
            raise RuntimeError(f"paper_walkforward_failed:{trade_date}:{(last or {}).get('failure')}")
        time.sleep(max(0.25, poll_seconds))
    raise TimeoutError(f"paper_walkforward_timeout:{trade_date}:{last}")


def _reports(base_url: str, session_id: str) -> list[dict[str, Any]]:
    status, body = _api(
        base_url,
        "GET",
        f"/api/paper/{session_id}/reports?light=true&paged=true&limit=1000",
    )
    if status >= 400:
        raise RuntimeError(f"paper_reports_unavailable:{status}:{body}")
    return body if isinstance(body, list) else list(body.get("items") or [])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a resumable, real 21-trading-day LEAN Paper walk-forward acceptance."
    )
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--source-backtest-id", required=True)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--days", type=int, default=21)
    parser.add_argument("--session-id")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout-per-day", type=int, default=900)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--evidence-out")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.days < 1:
        parser.error("--days must be positive")
    calendar = trade_dates_between("china", args.start_date, "2099-12-31")
    trade_dates = [item for item in calendar if item >= args.start_date][: args.days]
    if len(trade_dates) != args.days:
        raise RuntimeError(f"trade_calendar_incomplete:{len(trade_dates)}/{args.days}")
    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "planned",
                    "projectId": args.project_id,
                    "sourceBacktestId": args.source_backtest_id,
                    "tradeDates": trade_dates,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    session_id = str(args.session_id or "")
    if not session_id:
        status, session = _api(
            args.api_url,
            "POST",
            "/api/paper",
            {
                "name": f"LEAN 21-day acceptance {args.start_date}",
                "mode": "lean_walkforward",
                "projectId": args.project_id,
                "sourceBacktestId": args.source_backtest_id,
                "startDate": args.start_date,
                "autoAdvance": False,
            },
        )
        if status >= 400:
            raise RuntimeError(f"paper_session_create_failed:{status}:{session}")
        session_id = str(session["id"])

    completed: list[dict[str, Any]] = []
    for index, trade_date in enumerate(trade_dates, start=1):
        status, runs_body = _api(args.api_url, "GET", f"/api/paper/{session_id}/runs")
        if status >= 400:
            raise RuntimeError(f"paper_runs_unavailable:{status}:{runs_body}")
        runs = runs_body if isinstance(runs_body, list) else list(runs_body.get("items") or [])
        existing = _run_for_date(runs, trade_date)
        if str((existing or {}).get("status") or "") == "success":
            completed.append(existing or {})
            print(f"[{index}/{len(trade_dates)}] {trade_date} already success", flush=True)
            continue
        print(f"[{index}/{len(trade_dates)}] queue {trade_date}", flush=True)
        status, response = _api(
            args.api_url,
            "POST",
            f"/api/paper/{session_id}/run-day",
            {"tradeDate": trade_date, "autoSignal": False},
        )
        if status >= 400:
            raise RuntimeError(f"paper_run_day_failed:{trade_date}:{status}:{response}")
        item = _wait_for_run(
            args.api_url,
            session_id,
            trade_date,
            timeout_seconds=args.timeout_per_day,
            poll_seconds=args.poll_seconds,
        )
        completed.append(item)
        print(
            f"[{index}/{len(trade_dates)}] {trade_date} success "
            f"backtest={_field(item, 'backtest_run_id', 'backtestRunId')}",
            flush=True,
        )

    reports = _reports(args.api_url, session_id)
    status, detail = _api(args.api_url, "GET", f"/api/paper/{session_id}")
    if status >= 400:
        raise RuntimeError(f"paper_detail_unavailable:{status}:{detail}")
    before_counts = {
        "runs": len(detail.get("runs") or []),
        "reports": len(reports),
        "orders": len(detail.get("orders") or []),
        "snapshots": len(detail.get("snapshots") or []),
    }
    orders = [item for item in (detail.get("orders") or []) if isinstance(item, dict)]
    filled_orders = [
        item
        for item in orders
        if str(item.get("status") or "").lower() in {"3", "filled", "success", "completed"}
    ]
    rejected_orders = [
        item for item in orders if str(item.get("status") or "").lower() == "rejected"
    ]
    duplicate_status, duplicate_body = _api(
        args.api_url,
        "POST",
        f"/api/paper/{session_id}/run-day",
        {"tradeDate": trade_dates[-1], "autoSignal": False},
    )
    reports_after = _reports(args.api_url, session_id)
    _, detail_after = _api(args.api_url, "GET", f"/api/paper/{session_id}")
    after_counts = {
        "runs": len(detail_after.get("runs") or []),
        "reports": len(reports_after),
        "orders": len(detail_after.get("orders") or []),
        "snapshots": len(detail_after.get("snapshots") or []),
    }

    successful_dates = {
        str(_field(item, "trade_date", "tradeDate") or "")
        for item in completed
        if str(item.get("status") or "") == "success"
    }
    reconciliation_failures = [
        str(_field(item, "trade_date", "tradeDate") or "")
        for item in completed
        if (item.get("reconciliation") or {}).get("passed") is not True
    ]
    report_dates = {
        str(_field(item, "trade_date", "tradeDate") or "")
        for item in reports
    }
    walkforward_passed = bool(
        successful_dates == set(trade_dates)
        and set(trade_dates) <= report_dates
        and not reconciliation_failures
        and duplicate_status == 400
        and before_counts["reports"] == after_counts["reports"]
        and before_counts["orders"] == after_counts["orders"]
        and before_counts["snapshots"] == after_counts["snapshots"]
    )
    # The independent PR-01 definition additionally requires both a real fill
    # and a policy rejection in the same accepted session. A cumulative LEAN
    # run with no rejected intent is useful evidence, but must not be promoted
    # to LEVEL5_REPLAY_PASS.
    passed = bool(walkforward_passed and filled_orders and rejected_orders)
    result = {
        "status": "passed" if passed else ("partial" if walkforward_passed else "failed"),
        "sessionId": session_id,
        "sourceBacktestId": args.source_backtest_id,
        "projectId": args.project_id,
        "tradeDates": trade_dates,
        "successfulDays": len(successful_dates),
        "reportDays": len(set(trade_dates) & report_dates),
        "orders": before_counts["orders"],
        "filledOrders": len(filled_orders),
        "rejectedOrders": len(rejected_orders),
        "snapshots": before_counts["snapshots"],
        "reconciliationFailures": reconciliation_failures,
        "duplicateReplay": {
            "httpStatus": duplicate_status,
            "blocked": duplicate_status == 400,
            "detail": duplicate_body.get("detail") if isinstance(duplicate_body, dict) else None,
            "countsStable": before_counts == after_counts,
        },
        "walkforwardPassed": walkforward_passed,
        "level5ReplayRequirementsPassed": passed,
        "remainingRequirement": None if passed else "same_session_rejected_order_with_reason",
        "passed": passed,
    }
    encoded = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if args.evidence_out:
        evidence_path = Path(args.evidence_out).expanduser().resolve()
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
