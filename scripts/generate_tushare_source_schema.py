#!/usr/bin/env python3
"""Generate typed TuShare source tables from the checked-in contract snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACTS = ROOT / "config" / "tushare_contracts.v1.json"
DEFAULT_OUTPUT = ROOT / "web" / "backend" / "app" / "migrations" / "versions" / "0047_tushare_typed_source_tables.sql"
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
TYPE_SQL = {
    # Provider strings are intentionally unbounded source values. Canonical v2
    # tables impose business lengths; source tables must retain the exact input.
    "string": "longtext",
    "date": "date",
    "datetime": "datetime(6)",
    "integer": "bigint",
    "decimal": "decimal(38,8)",
    "boolean": "integer",
}


def _column(field: dict[str, object]) -> str:
    name = str(field["name"])
    if not IDENTIFIER.fullmatch(name):
        raise RuntimeError(f"Unsafe TuShare field identifier: {name}")
    sql_type = TYPE_SQL.get(str(field.get("type") or "string"), "text")
    return f"    `{name}` {sql_type}"


def _table_sql(contract: dict[str, object]) -> str:
    table = str(contract["sourceTable"])
    if not IDENTIFIER.fullmatch(table):
        raise RuntimeError(f"Unsafe TuShare source table identifier: {table}")
    fields = list(contract.get("fields") or [])
    columns = [
        # Use explicit bounded types for indexed metadata. The migration layer's
        # portable migration translation cannot infer quoted column names.
        "    `_observation_id` varchar(64) primary key",
        "    `_batch_id` varchar(64) not null",
        "    `_natural_key_hash` varchar(64) not null",
        "    `_revision_no` integer not null",
        "    `_is_current` integer not null default 1",
        "    `_current_natural_key_hash` varchar(64) generated always as (case when `_is_current` = 1 then `_natural_key_hash` else null end) stored",
        "    `_published_at` datetime(6)",
        "    `_source_updated_at` datetime(6)",
        "    `_observed_at` datetime(6) not null",
        "    `_valid_from` datetime(6)",
        "    `_valid_to` datetime(6)",
        "    `_payload_hash` varchar(64) not null",
        *[_column(field) for field in fields],
        "    unique(`_natural_key_hash`,`_revision_no`)",
        "    unique(`_current_natural_key_hash`)",
        "    check (`_revision_no` > 0)",
        "    check (`_is_current` in (0,1))",
        "    check (`_valid_to` is null or `_valid_from` is null or `_valid_to` >= `_valid_from`)",
    ]
    return (
        f"create table if not exists `{table}` (\n"
        + ",\n".join(columns)
        + "\n);\n\n"
        + f"create index if not exists `idx_{table}_current`\n"
        + f"    on `{table}`(`_natural_key_hash`,`_is_current`);\n"
        + f"create index if not exists `idx_{table}_observed`\n"
        + f"    on `{table}`(`_observed_at`);\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contracts", type=Path, default=DEFAULT_CONTRACTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = json.loads(args.contracts.read_text(encoding="utf-8"))
    contracts = list(payload.get("contracts") or [])
    if not contracts:
        raise RuntimeError("The TuShare contract snapshot is empty.")
    tables = [_table_sql(contract) for contract in contracts]
    header = (
        "-- description: Add contract-generated typed source tables for TuShare stock, index, futures and options data\n"
        "-- rollback: stop TuShare ingestion, retain raw archives, and remove generated source tables through a reviewed forward migration\n"
        f"-- generated from contract version {payload['contractVersion']}; do not edit by hand\n\n"
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(header + "\n".join(tables), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "tables": len(tables)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
