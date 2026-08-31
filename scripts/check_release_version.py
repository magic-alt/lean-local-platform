#!/usr/bin/env python3
"""Validate the repository SemVer authority and release changelog contract."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


def read_version() -> str:
    path = ROOT / "VERSION"
    if not path.is_file():
        raise ValueError("VERSION file is missing")
    version = path.read_text(encoding="utf-8").strip()
    if not version:
        raise ValueError("VERSION is empty")
    if not SEMVER_RE.fullmatch(version):
        raise ValueError(f"VERSION is not valid SemVer: {version!r}")
    return version


def validate_tag(version: str, tag: str) -> None:
    expected = f"v{version}"
    if tag != expected:
        raise ValueError(f"release tag {tag!r} does not match VERSION; expected {expected!r}")


def validate_changelog(version: str) -> None:
    path = ROOT / "CHANGELOG.md"
    if not path.is_file():
        raise ValueError("CHANGELOG.md is missing")
    text = path.read_text(encoding="utf-8")
    escaped = re.escape(version)
    heading = re.compile(
        rf"^##\s+(?:\[{escaped}\]|{escaped})\s+-\s+\d{{4}}-\d{{2}}-\d{{2}}\s*$",
        re.MULTILINE,
    )
    if not heading.search(text):
        raise ValueError(
            "CHANGELOG.md is missing the dated release heading; expected "
            f"'## [{version}] - YYYY-MM-DD'"
        )
    if not re.search(r"^##\s+Unreleased\s*$", text, re.MULTILINE):
        raise ValueError("CHANGELOG.md must retain a fresh '## Unreleased' section")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", help="Release tag, for example v0.1.0")
    parser.add_argument(
        "--require-changelog",
        action="store_true",
        help="Require a dated changelog heading for VERSION",
    )
    args = parser.parse_args()

    try:
        version = read_version()
        if args.tag:
            validate_tag(version, args.tag)
        if args.require_changelog:
            validate_changelog(version)
    except ValueError as exc:
        print(f"release version validation failed: {exc}", file=sys.stderr)
        return 1

    print(f"release version validation passed: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
