#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import DATA_DIR  # noqa: E402
from app.db import init_db  # noqa: E402
from app.services.data_releases import publish_data_release  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish an immutable composite DataRelease v2")
    parser.add_argument("--spec", required=True, help="JSON release specification")
    parser.add_argument("--data-root", help="Shared data root; defaults to QUANT_DATA_ROOT or platform DATA_DIR")
    parser.add_argument("--dry-run", action="store_true", help="Validate and freeze without writing MySQL registry state")
    args = parser.parse_args()
    spec_path = Path(args.spec).expanduser().resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if not isinstance(spec, dict):
        raise ValueError("DataRelease specification must be a JSON object")
    data_root = Path(args.data_root or os.environ.get("QUANT_DATA_ROOT") or DATA_DIR).expanduser().resolve()
    if not args.dry_run:
        init_db()
    manifest = publish_data_release(spec, data_root, persist=not args.dry_run)
    print(json.dumps({"dataReleaseId": manifest["dataReleaseId"], "manifestSha256": manifest["manifestSha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
