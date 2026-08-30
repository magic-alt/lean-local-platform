#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage the frozen Windows Native qualification data.")
    parser.add_argument("--spec", required=True)
    args = parser.parse_args()

    if os.environ.get("LEAN_WINDOWS_PRODUCTION_MODE", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        raise SystemExit("acceptance_fixture_refuses_production_mode")

    spec_path = Path(args.spec).resolve()
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    if payload.get("qualificationId") != "windows-native-core-v1":
        raise SystemExit("unsupported_windows_native_acceptance_spec")
    fixture = payload.get("fixture")
    if not isinstance(fixture, dict) or not isinstance(fixture.get("rows"), list):
        raise SystemExit("windows_native_acceptance_fixture_missing")
    parameters = payload.get("parameters")
    if (
        not isinstance(parameters, dict)
        or str(parameters.get("ticker")) != str(fixture.get("symbol"))
        or str(parameters.get("market")) != str(fixture.get("market"))
    ):
        raise SystemExit("windows_native_acceptance_fixture_binding_invalid")

    sys.path.insert(0, str(BACKEND))
    from app.lean_engine.data_paths import daily_zip_path
    from app.lean_engine.data_writers import lean_price, normalize_rows, write_lean_daily_zip

    symbol = str(fixture["symbol"])
    market = str(fixture["market"])
    rows = list(fixture["rows"])
    normalized = normalize_rows(rows)
    expected_csv = "".join(
        (
            f"{item_date:%Y%m%d} 00:00,{lean_price(open_price)},"
            f"{lean_price(high)},{lean_price(low)},{lean_price(close)},{volume}\n"
        )
        for item_date, open_price, high, low, close, volume in normalized
    )
    output = daily_zip_path(symbol, market)
    if output.exists():
        try:
            with zipfile.ZipFile(output) as archive:
                actual_csv = archive.read(f"{symbol.lower()}.csv").decode("utf-8")
        except (OSError, KeyError, UnicodeDecodeError, zipfile.BadZipFile) as exc:
            raise SystemExit("windows_native_acceptance_fixture_conflict") from exc
        if actual_csv != expected_csv:
            raise SystemExit("windows_native_acceptance_fixture_conflict")
        result = {
            "symbol": symbol,
            "market": market,
            "rows": len(normalized),
            "first_date": normalized[0][0].isoformat(),
            "last_date": normalized[-1][0].isoformat(),
        }
    else:
        result = write_lean_daily_zip(
            symbol=symbol,
            rows=rows,
            source=str(fixture["source"]),
            overwrite=False,
            market=market,
        )
    print(
        json.dumps(
            {
                "qualificationId": payload["qualificationId"],
                "symbol": result["symbol"],
                "market": result["market"],
                "rows": result["rows"],
                "firstDate": result["first_date"],
                "lastDate": result["last_date"],
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
