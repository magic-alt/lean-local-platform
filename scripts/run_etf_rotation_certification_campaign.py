#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "web" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.backtest_service import mark_backtest_queued  # noqa: E402
from app.services.etf_rotation_certification_campaign import (  # noqa: E402
    advance_campaign,
    campaign_status,
    start_campaign,
)
from app.services.tasks import update_task  # noqa: E402
from app.tasks.worker import (  # noqa: E402
    dispatch_experiment_batch_task,
    run_backtest_task,
)


BLOCKING_ACTIONS = {
    "canonical_failed",
    "canonical_attribution_incomplete",
    "rerun_failed",
    "rerun_attribution_incomplete",
    "deterministic_replay_failed",
    "baseline_failed",
    "baseline_attribution_incomplete",
    "walk_forward_failed",
    "walk_forward_evidence_missing",
    "waiting_paper_evidence",
    "paper_evidence_incomplete",
    "certification_failed",
}


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return payload


def _dispatch_backtest(job: dict[str, Any]) -> None:
    result = run_backtest_task.apply_async(
        args=[job["task_id"], job["id"]],
        queue="backtest",
    )
    update_task(
        str(job["task_id"]),
        celery_task_id=result.id,
        status="queued",
    )
    mark_backtest_queued(str(job["id"]))


def _dispatch_batch(batch: dict[str, Any]) -> None:
    dispatch_experiment_batch_task.apply_async(
        args=[batch["id"]],
        queue="default",
    )


def _compact(status: dict[str, Any]) -> dict[str, Any]:
    return {
        "campaignId": status.get("campaignId"),
        "status": status.get("status"),
        "stage": status.get("stage"),
        "action": status.get("action"),
        "dataReleaseId": status.get("dataReleaseId"),
        "details": status.get("details") or {},
    }


def _print(status: dict[str, Any]) -> None:
    print(json.dumps(_compact(status), ensure_ascii=False, indent=2, sort_keys=True, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the resumable ETF execution-certification campaign for Issue #67. "
            "The command dispatches existing LEAN/experiment workers and never enables Live/P9."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)

    start = commands.add_parser("start", help="Freeze campaign configuration and create a campaign ID.")
    start.add_argument("--config", type=Path, required=True)

    status = commands.add_parser("status", help="Read persisted campaign workflow evidence.")
    status.add_argument("--campaign-id", required=True)

    advance = commands.add_parser("advance", help="Advance one idempotent campaign step.")
    advance.add_argument("--campaign-id", required=True)

    run = commands.add_parser("run", help="Advance synchronously until certified, blocked, failed, or cycle limit.")
    run.add_argument("--campaign-id", required=True)
    run.add_argument("--poll-seconds", type=float, default=5.0)
    run.add_argument("--max-cycles", type=int, default=720)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "start":
        status = start_campaign(_load(args.config))
        _print(status)
        return 0
    if args.command == "status":
        status = campaign_status(args.campaign_id)
        _print(status)
        return 0
    if args.command == "advance":
        status = advance_campaign(
            args.campaign_id,
            dispatch_backtest=_dispatch_backtest,
            dispatch_batch=_dispatch_batch,
        )
        _print(status)
        return 0 if status.get("action") == "artifact_registered" else 2 if status.get("action") in BLOCKING_ACTIONS else 0

    poll_seconds = max(0.25, min(float(args.poll_seconds), 60.0))
    max_cycles = max(1, int(args.max_cycles))
    last_action = None
    for _ in range(max_cycles):
        status = advance_campaign(
            args.campaign_id,
            dispatch_backtest=_dispatch_backtest,
            dispatch_batch=_dispatch_batch,
        )
        action = status.get("action")
        if action != last_action:
            _print(status)
            last_action = action
        if action == "artifact_registered":
            return 0
        if action in BLOCKING_ACTIONS:
            return 2
        time.sleep(poll_seconds)
    status = campaign_status(args.campaign_id)
    _print(status)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
