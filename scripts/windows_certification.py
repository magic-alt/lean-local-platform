#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.windows_certification import (  # noqa: E402
    DEFAULT_CERTIFICATE_PATH,
    issue_windows_certificate,
    verify_windows_certificate,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Issue or verify the Windows Celery certification gate.")
    parser.add_argument("action", choices=("issue", "verify"))
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--certificate", type=Path, default=DEFAULT_CERTIFICATE_PATH)
    args = parser.parse_args()
    if args.action == "issue":
        if args.evidence is None:
            parser.error("--evidence is required when issuing a certificate")
        result = issue_windows_certificate(args.evidence.resolve(), args.certificate.resolve())
        print(json.dumps(result, indent=2))
        return 0
    result = verify_windows_certificate(args.certificate.resolve())
    print(json.dumps(result, indent=2))
    return 0 if result["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
