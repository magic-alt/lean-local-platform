from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..core.config import (
    DEFAULT_DOCKER_IMAGE,
    DEFAULT_RESEARCH_IMAGE,
    JOB_TIMEOUT_SECONDS,
    LEAN_DEPLOYMENT_MODE,
    LEAN_DEPLOYMENT_PROFILE,
    LEAN_EXECUTION_BACKEND,
    LOG_LEVEL,
    MAX_CONCURRENT_JOBS,
)
from ..db import db, json_dump, utc_now


_SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
_LEGACY_DYNAMIC_END_SENTINEL = "2026-07-13"


def _current_shanghai_date() -> str:
    return datetime.now(_SHANGHAI_TZ).date().isoformat()


DEFAULT_SETTINGS: dict[str, Any] = {
    "defaultAssetClass": "equity",
    "defaultMarket": "china",
    "defaultVenue": "china",
    "defaultResolution": "daily",
    "defaultDataType": "trade",
    "defaultProvider": "tushare",
    "defaultAdjust": "",
    "defaultStrategyTemplate": "ema_cross",
    "defaultCash": 300000,
    "defaultStart": "2024-01-01",
    # Kept here for the public/default-settings shape and allowed-key set. The
    # effective default is resolved in get_settings() so a long-lived process
    # cannot freeze yesterday's Shanghai calendar date at module import time.
    "defaultEnd": _current_shanghai_date(),
    "dockerImage": DEFAULT_DOCKER_IMAGE,
    "researchImage": DEFAULT_RESEARCH_IMAGE,
    "chartPointLimit": 1000000,
    "maxConcurrentJobs": MAX_CONCURRENT_JOBS,
    "maxBatchRuns": 5000,
    "jobTimeoutSeconds": JOB_TIMEOUT_SECONDS,
    "logLevel": LOG_LEVEL,
}

ALLOWED_KEYS = set(DEFAULT_SETTINGS)


def get_settings() -> dict[str, Any]:
    values = dict(DEFAULT_SETTINGS)
    values["defaultEnd"] = _current_shanghai_date()
    with db() as connection:
        rows = connection.execute("select key, value_json from settings").fetchall()
    for row in rows:
        key = row["key"]
        if key in ALLOWED_KEYS:
            import json

            values[key] = json.loads(row["value_json"])
    if values.get("defaultEnd") == _LEGACY_DYNAMIC_END_SENTINEL:
        values["defaultEnd"] = _current_shanghai_date()
    values["deploymentMode"] = LEAN_DEPLOYMENT_MODE
    values["deploymentProfile"] = LEAN_DEPLOYMENT_PROFILE
    values["executionBackend"] = LEAN_EXECUTION_BACKEND
    return values


def update_settings(updates: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    clean = {key: value for key, value in updates.items() if key in ALLOWED_KEYS}
    with db() as connection:
        for key, value in clean.items():
            connection.execute(
                """
                insert into settings (key, value_json, updated_at)
                values (?, ?, ?)
                on conflict(key) do update set
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """,
                (key, json_dump(value), now),
            )
    return get_settings()
