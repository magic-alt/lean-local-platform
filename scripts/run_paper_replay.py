#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db import init_db
from app.services.paper import run_replay


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Paper Replay session over a date range.")
    parser.add_argument("session_id")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--no-auto-signal", action="store_true")
    args = parser.parse_args()

    init_db()
    result = run_replay(args.session_id, args.start_date, args.end_date, auto_signal=not args.no_auto_signal)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
