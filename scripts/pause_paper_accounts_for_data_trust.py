#!/usr/bin/env python3
"""Pause runnable Paper accounts during the Level 5 valuation-trust incident."""
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.paper_accounts import pause_accounts_for_data_trust  # noqa: E402


def main() -> int:
    print(json.dumps(pause_accounts_for_data_trust(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
