from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ITEM_MARKER = "LEAN_SCREENING|"
SUMMARY_MARKER = "LEAN_SCREENING_SUMMARY|"
SCREENING_REPORT_NAME = "screening-report.json"


def _marked_payload(line: str, marker: str) -> dict[str, Any] | None:
    if marker not in line:
        return None
    raw = line.split(marker, 1)[1].strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def extract_screening_report(results_dir: Path) -> Path | None:
    """Extract the strategy's structured final screening snapshot from LEAN logs."""
    summary: dict[str, Any] | None = None
    items_by_symbol: dict[str, dict[str, Any]] = {}
    for name in ("log.txt", "stdout.log"):
        path = results_dir / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            summary_payload = _marked_payload(line, SUMMARY_MARKER)
            if summary_payload is not None:
                summary = summary_payload
                continue
            item = _marked_payload(line, ITEM_MARKER)
            if item is None:
                continue
            symbol = str(item.get("symbol") or "").strip().upper()
            if symbol:
                items_by_symbol[symbol] = item
    if summary is None and not items_by_symbol:
        return None
    items = [items_by_symbol[symbol] for symbol in sorted(items_by_symbol)]
    qualified = [
        item for item in sorted(
            (row for row in items if row.get("suitableToBuy")),
            key=lambda row: (-float(row.get("overallScore") or 0), str(row.get("symbol") or "")),
        )
    ]
    selected_symbols = {str(symbol) for symbol in (summary or {}).get("selected") or []}
    payload = {
        "schemaVersion": int((summary or {}).get("schemaVersion") or 1),
        "mode": (summary or {}).get("mode") or "screening",
        "tradeSimulation": bool((summary or {}).get("tradeSimulation", False)),
        "asOfDate": (summary or {}).get("asOfDate"),
        "universeCode": (summary or {}).get("universeCode"),
        "summary": summary or {},
        "items": items,
        "qualified": qualified,
        "selected": [item for item in qualified if str(item.get("symbol") or "") in selected_symbols],
    }
    output = results_dir / SCREENING_REPORT_NAME
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output
