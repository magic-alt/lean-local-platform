#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sdk" / "python"))

from lean_local_platform import WorkflowClient, WorkflowClientError  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="workflowctl",
        description="Thin client for integrated research-to-Paper workflow status and recovery decisions.",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("LEAN_API_URL", "http://127.0.0.1:8000"),
        help="Platform API base URL; defaults to LEAN_API_URL or loopback API.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "plan", "explain", "resume"):
        command = sub.add_parser(name)
        command.add_argument("import_id")
    compare = sub.add_parser("compare")
    compare.add_argument("left_import_id")
    compare.add_argument("right_import_id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    client = WorkflowClient(args.base_url, token=os.environ.get("LEAN_API_TOKEN"))
    try:
        if args.command == "status":
            result = client.status(args.import_id)
        elif args.command == "plan":
            result = client.plan(args.import_id)
        elif args.command == "explain":
            result = client.explain(args.import_id)
        elif args.command == "resume":
            result = client.resume(args.import_id)
        elif args.command == "compare":
            result = client.compare(args.left_import_id, args.right_import_id)
        else:
            parser = build_parser()
            parser.error("unsupported command")
            return 2
    except WorkflowClientError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
