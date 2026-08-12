#!/usr/bin/env python3
"""Validate the checked-in TuShare contract and optionally probe live samples.

The default check is offline and deterministic. ``--live-sample`` performs four
bounded, read-only provider calls and never prints the configured token.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.tushare_adapter import TushareAdapter  # noqa: E402
from app.services.tushare_contracts import contract_for, contract_snapshot  # noqa: E402


MIGRATION = BACKEND / "app" / "migrations" / "versions" / "0047_tushare_typed_source_tables.sql"
LIVE_PROBES = {
    "stock_basic": {"exchange": "", "list_status": "L"},
    "index_basic": {"market": "SSE"},
    "fut_basic": {"exchange": "CFFEX", "fut_type": "1"},
    "opt_basic": {"exchange": "SSE"},
}


def _records(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, list):
        return [dict(item) for item in value]
    if hasattr(value, "to_dict"):
        return [dict(item) for item in value.to_dict("records")]
    return []


def validate_offline() -> dict[str, Any]:
    snapshot = contract_snapshot()
    contracts = snapshot["contracts"]
    migration = MIGRATION.read_text(encoding="utf-8")
    declared_tables = set(
        re.findall(r"create table if not exists `([a-z][a-z0-9_]*)`", migration)
    )
    expected_tables = {str(item["sourceTable"]) for item in contracts}
    problems: list[str] = []
    if declared_tables != expected_tables:
        problems.append("generated_source_table_set_mismatch")
    for contract in contracts:
        field_names = [str(field["name"]) for field in contract["fields"]]
        if len(field_names) != len(set(field_names)):
            problems.append(f"duplicate_fields:{contract['datasetKey']}")
        if not set(contract["naturalKey"]) <= set(field_names):
            problems.append(f"natural_key_not_in_fields:{contract['datasetKey']}")
    return {
        "valid": not problems,
        "contractVersion": snapshot["contractVersion"],
        "asOfDate": snapshot["asOfDate"],
        "datasets": len(contracts),
        "active": sum(item["status"] == "active" for item in contracts),
        "retired": sum(item["status"] == "retired" for item in contracts),
        "assetClasses": dict(sorted(Counter(item["assetClass"] for item in contracts).items())),
        "storageTiers": dict(sorted(Counter(item["storageTier"] for item in contracts).items())),
        "typedSourceTables": len(declared_tables),
        "problems": problems,
    }


def validate_live_samples(pro: Any) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for api_name, params in LIVE_PROBES.items():
        contract = contract_for(api_name)
        if contract is None:
            results.append({"apiName": api_name, "status": "contract_missing"})
            continue
        expected = {str(field["providerName"]) for field in contract["fields"]}
        fields = ",".join(sorted(expected))
        try:
            rows = _records(pro.query(api_name, fields=fields, limit=1, **params))
        except Exception as exc:  # Provider errors are audit output, not secrets.
            message = str(exc)
            lowered = message.lower()
            denied = any(token in lowered for token in ("权限", "permission", "积分"))
            results.append(
                {
                    "apiName": api_name,
                    "assetClass": contract["assetClass"],
                    "status": "permission_denied" if denied else "provider_error",
                    "error": message[:500],
                }
            )
            continue
        if not rows:
            results.append(
                {"apiName": api_name, "assetClass": contract["assetClass"], "status": "empty"}
            )
            continue
        returned = set(rows[0])
        unexpected = sorted(returned - expected)
        results.append(
            {
                "apiName": api_name,
                "assetClass": contract["assetClass"],
                "status": "field_drift" if unexpected else "valid",
                "returnedFields": len(returned),
                "unexpectedFields": unexpected,
            }
        )
    return {
        "valid": all(item["status"] in {"valid", "empty", "permission_denied"} for item in results),
        "samples": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-sample", action="store_true", help="Call four representative TuShare APIs.")
    args = parser.parse_args()
    report: dict[str, Any] = {"offline": validate_offline()}
    if args.live_sample:
        report["live"] = validate_live_samples(TushareAdapter().pro)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["offline"]["valid"] and report.get("live", {"valid": True})["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
