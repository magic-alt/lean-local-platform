from __future__ import annotations

from datetime import datetime


CREATED = "created"
QUEUED = "queued"
RUNNING = "running"
SUCCESS = "success"
FAILED = "failed"
CANCELLED = "cancelled"

BACKTEST_STATUSES = {CREATED, QUEUED, RUNNING, SUCCESS, FAILED, CANCELLED}
TERMINAL_STATUSES = {SUCCESS, FAILED, CANCELLED}
ACTIVE_STATUSES = {CREATED, QUEUED, RUNNING}

LEGACY_STATUS_MAP = {
    "succeeded": SUCCESS,
    "interrupted": FAILED,
}


def normalize_status(value: str | None) -> str:
    status = (value or CREATED).strip().lower()
    status = LEGACY_STATUS_MAP.get(status, status)
    if status not in BACKTEST_STATUSES:
        raise ValueError(f"Unsupported backtest status: {value!r}")
    return status


def is_terminal(status: str | None) -> bool:
    return normalize_status(status) in TERMINAL_STATUSES


def duration_seconds(started_at: str | None, finished_at: str | None) -> float | None:
    if not started_at or not finished_at:
        return None
    try:
        started = datetime.fromisoformat(started_at)
        finished = datetime.fromisoformat(finished_at)
    except ValueError:
        return None
    return max(0.0, round((finished - started).total_seconds(), 3))
