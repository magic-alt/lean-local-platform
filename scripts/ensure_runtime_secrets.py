#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import secrets
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SECRETS_DIR = ROOT / "web" / "runtime" / "secrets"


def ensure_secret(path: Path, *, rotate: bool = False) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not rotate:
        os.chmod(path, 0o600)
        return "existing"
    value = secrets.token_urlsafe(48) + "\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, value.encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    os.chmod(path, 0o600)
    return "rotated" if rotate else "created"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create non-versioned runtime service secrets.")
    parser.add_argument("--rotate-runner-token", action="store_true")
    args = parser.parse_args()
    status = ensure_secret(
        SECRETS_DIR / "runner_token",
        rotate=args.rotate_runner_token,
    )
    print(f"runner_token={status};mode={oct((SECRETS_DIR / 'runner_token').stat().st_mode & 0o777)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
