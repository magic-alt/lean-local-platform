#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from collections import ChainMap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
sys.path.insert(0, str(BACKEND))

from app.runners.dotnet import DOTNET_PATH_ENV, dotnet_major_available, resolve_dotnet


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve and qualify the host dotnet executable.")
    parser.add_argument("--path")
    parser.add_argument("--require", choices=("runtime", "sdk"), default="runtime")
    parser.add_argument("--major", type=int, default=10)
    args = parser.parse_args()

    overrides = {DOTNET_PATH_ENV: args.path} if args.path else {}
    executable = resolve_dotnet(environment=ChainMap(overrides, os.environ))
    if executable is None:
        print("dotnet_executable_missing", file=sys.stderr)
        return 2
    if not dotnet_major_available(
        executable,
        major=args.major,
        sdk=args.require == "sdk",
    ):
        print(f"dotnet_{args.require}_{args.major}_missing", file=sys.stderr)
        return 2
    print(executable)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
