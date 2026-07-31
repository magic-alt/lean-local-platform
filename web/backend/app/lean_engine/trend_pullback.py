from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ITEM_MARKER = "LEAN_TREND_PULLBACK|"
SUMMARY_MARKER = "LEAN_TREND_PULLBACK_SUMMARY|"
REPORT_NAME = "trend-pullback-decisions.json"


def _payload(line: str, marker: str) -> dict[str, Any] | None:
    if marker not in line:
        return None
    try:
        value = json.loads(line.split(marker, 1)[1].strip())
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def extract_trend_pullback_report(results_dir: Path) -> Path | None:
    decisions: dict[tuple[str, str], dict[str, Any]] = {}
    summaries: dict[str, dict[str, Any]] = {}
    for name in ("log.txt", "stdout.log"):
        path = results_dir / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            summary = _payload(line, SUMMARY_MARKER)
            if summary is not None and summary.get("date"):
                summaries[str(summary["date"])] = summary
                continue
            item = _payload(line, ITEM_MARKER)
            if item is not None and item.get("date") and item.get("symbol"):
                decisions[(str(item["date"]), str(item["symbol"]).upper())] = item
    if not decisions and not summaries:
        return None
    payload = {
        "schemaVersion": 1,
        "mode": "ashare_trend_pullback_portfolio",
        "tradeSimulation": True,
        "summaries": [summaries[key] for key in sorted(summaries)],
        "decisions": [decisions[key] for key in sorted(decisions)],
    }
    output = results_dir / REPORT_NAME
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output
