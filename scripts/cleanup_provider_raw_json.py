#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1] / "web" / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.provider_raw_cleanup import (  # noqa: E402
    cleanup_legacy_provider_json,
    legacy_json_inventory,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive and clear legacy provider row JSON.")
    parser.add_argument("--execute", action="store_true", help="Perform cleanup; default is inventory only.")
    parser.add_argument("--archive-batch-size", type=int, default=20_000)
    parser.add_argument("--clear-batch-size", type=int, default=250_000)
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps(legacy_json_inventory(), ensure_ascii=False, sort_keys=True))
        return 0

    def progress(payload: dict[str, object]) -> None:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)

    result = cleanup_legacy_provider_json(
        archive_batch_size=args.archive_batch_size,
        clear_batch_size=args.clear_batch_size,
        callback=progress,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
