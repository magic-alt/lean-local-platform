#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Iterable


CHANGELOG_PATH = "CHANGELOG.md"


def staged_files() -> list[str]:
    completed = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def changelog_is_present(paths: Iterable[str]) -> bool:
    return CHANGELOG_PATH in set(paths)


def main() -> int:
    parser = argparse.ArgumentParser(description="Require CHANGELOG.md in every repository commit.")
    parser.add_argument("--staged", action="store_true", help="Validate the staged Git index.")
    parser.parse_args()

    paths = staged_files()
    if changelog_is_present(paths):
        return 0
    print(
        "commit blocked: stage a concise CHANGELOG.md entry for this commit. "
        "Self commit hashes are not required.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
