#!/usr/bin/env python3
"""Read-only audit of GitHub repository settings against versioned policy."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.github.com"


def _request(path: str, token: str | None) -> urllib.request.Request:
    request = urllib.request.Request(
        f"{API}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "lean-local-platform-governance-audit",
        },
    )
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    return request


def api_get(path: str, token: str | None) -> Any:
    with urllib.request.urlopen(_request(path, token), timeout=15) as response:
        return json.load(response)


def api_status(path: str, token: str | None) -> int:
    try:
        with urllib.request.urlopen(_request(path, token), timeout=15) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


def expected_metadata() -> tuple[str, list[str]]:
    path = ROOT / ".github/repository-metadata.yml"
    lines = path.read_text(encoding="utf-8").splitlines()
    description_parts: list[str] = []
    topics: list[str] = []
    in_description = False
    in_topics = False
    for line in lines:
        if line.startswith("description:"):
            in_description = True
            in_topics = False
            continue
        if line.startswith("topics:"):
            in_description = False
            in_topics = True
            continue
        if in_description and line.startswith("  ") and line.strip():
            description_parts.append(line.strip())
        elif in_topics and line.startswith("  - "):
            topics.append(line[4:].strip())
    return " ".join(description_parts), topics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repository",
        default=os.environ.get("GITHUB_REPOSITORY", "magic-alt/lean-local-platform"),
        help="owner/repository",
    )
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    policy = json.loads((ROOT / ".github/repository-policy.json").read_text(encoding="utf-8"))
    expected_description, expected_topics = expected_metadata()
    owner, repo = args.repository.split("/", 1)

    errors: list[str] = []
    try:
        metadata = api_get(f"/repos/{owner}/{repo}", token)
        branch = api_get(f"/repos/{owner}/{repo}/branches/main", token)
        rulesets = api_get(f"/repos/{owner}/{repo}/rulesets", token)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        print(f"repository settings audit could not read GitHub API: {exc}", file=sys.stderr)
        return 2

    expected_repo = policy["repository"]
    for key, expected in expected_repo.items():
        actual = metadata.get(key)
        if actual != expected:
            errors.append(f"repository.{key}: expected {expected!r}, got {actual!r}")

    if metadata.get("description") != expected_description:
        errors.append(
            f"repository.description: expected {expected_description!r}, got {metadata.get('description')!r}"
        )

    actual_topics = sorted(metadata.get("topics") or [])
    if actual_topics != sorted(expected_topics):
        errors.append(
            "repository.topics: expected "
            f"{sorted(expected_topics)!r}, got {actual_topics!r}"
        )

    if not branch.get("protected"):
        errors.append("main: branch is not protected by branch protection/rulesets")

    actual_rulesets = {
        item.get("name"): item
        for item in rulesets
        if isinstance(item, dict) and item.get("name")
    }
    for expected in policy.get("rulesets", []):
        actual = actual_rulesets.get(expected["name"])
        if actual is None:
            errors.append(f"ruleset missing: {expected['name']}")
            continue
        if actual.get("enforcement") != expected.get("enforcement"):
            errors.append(
                f"ruleset {expected['name']!r} enforcement: "
                f"expected {expected.get('enforcement')!r}, got {actual.get('enforcement')!r}"
            )
        if actual.get("target") != expected.get("target"):
            errors.append(
                f"ruleset {expected['name']!r} target: "
                f"expected {expected.get('target')!r}, got {actual.get('target')!r}"
            )

    security = policy.get("security") or {}
    if security.get("dependency_graph_required"):
        status = api_status(f"/repos/{owner}/{repo}/dependency-graph/sbom", token)
        if status != 200:
            errors.append(
                "security.dependency_graph: expected enabled/readable, "
                f"GitHub dependency-graph SBOM endpoint returned HTTP {status}"
            )

    if errors:
        print("GitHub repository settings drift detected:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        print(
            "See docs/repository-governance.md for the intended server-side settings.",
            file=sys.stderr,
        )
        return 1

    print("GitHub repository settings match the versioned governance baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
