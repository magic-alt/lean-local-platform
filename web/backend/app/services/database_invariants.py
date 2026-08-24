from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..db import database_backend


BASELINE_MANIFEST = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "postgres"
    / "baseline_manifest.json"
)


class ControlPlaneStorageViolation(RuntimeError):
    """Raised when market time-series storage crosses into the control plane."""


def forbidden_market_relations() -> frozenset[str]:
    payload = json.loads(BASELINE_MANIFEST.read_text(encoding="utf-8"))
    return frozenset(str(item).lower() for item in payload["forbiddenRelations"])


def assert_control_plane_schema(connection: Any) -> None:
    """Fail closed if a forbidden market fact table exists in the control DB."""

    backend = database_backend()
    if backend == "postgresql":
        rows = connection.execute(
            """
            select table_name from information_schema.tables
            where table_schema=current_schema() and table_type='BASE TABLE'
            """
        ).fetchall()
        present = {str(row["table_name"]).lower() for row in rows}
    elif backend == "sqlite":
        rows = connection.execute(
            "select name from sqlite_master where type='table'"
        ).fetchall()
        present = {str(row["name"]).lower() for row in rows}
    else:
        rows = connection.execute("show full tables where Table_type='BASE TABLE'").fetchall()
        present = {
            str(next(iter(dict(row).values()))).lower()
            for row in rows
            if dict(row)
        }
    violations = sorted(present & forbidden_market_relations())
    if violations:
        raise ControlPlaneStorageViolation(
            "CONTROL_PLANE_MARKET_DATA_RELATION_FORBIDDEN: " + ", ".join(violations)
        )


def assert_typed_source_write_allowed(contract: dict[str, Any]) -> None:
    table = str(contract.get("sourceTable") or "").strip().lower()
    tier = str(contract.get("storageTier") or "").strip().lower()
    if tier == "columnar" or table in forbidden_market_relations():
        raise ControlPlaneStorageViolation(
            f"CONTROL_PLANE_MARKET_DATA_WRITE_FORBIDDEN:{table or 'unknown'}"
        )
