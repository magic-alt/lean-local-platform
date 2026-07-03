from typing import Any

from ..core.config import DEFAULT_DOCKER_IMAGE, DEFAULT_RESEARCH_IMAGE
from ..db import db, json_dump, utc_now


DEFAULT_SETTINGS: dict[str, Any] = {
    "defaultAssetClass": "equity",
    "defaultMarket": "usa",
    "defaultVenue": "usa",
    "defaultResolution": "daily",
    "defaultDataType": "trade",
    "defaultProvider": "yahoo",
    "defaultAdjust": "",
    "defaultStrategyTemplate": "ema_cross",
    "defaultCash": 100000,
    "defaultStart": "2018-01-01",
    "defaultEnd": "2024-12-31",
    "dockerImage": DEFAULT_DOCKER_IMAGE,
    "researchImage": DEFAULT_RESEARCH_IMAGE,
    "chartPointLimit": 1000000,
}

ALLOWED_KEYS = set(DEFAULT_SETTINGS)


def get_settings() -> dict[str, Any]:
    values = dict(DEFAULT_SETTINGS)
    with db() as connection:
        rows = connection.execute("select key, value_json from settings").fetchall()
    for row in rows:
        key = row["key"]
        if key in ALLOWED_KEYS:
            import json

            values[key] = json.loads(row["value_json"])
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
