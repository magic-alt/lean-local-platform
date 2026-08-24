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

from app.services.backend_parity import compare_results  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Docker and native LEAN result artifacts.")
    parser.add_argument("--docker-result", type=Path, required=True)
    parser.add_argument("--native-result", type=Path, required=True)
    parser.add_argument("--tolerance", type=float, default=1e-8)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = compare_results(args.docker_result, args.native_result, tolerance=args.tolerance)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
