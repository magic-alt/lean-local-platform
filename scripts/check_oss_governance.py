#!/usr/bin/env python3
"""Validate open-source governance files without third-party dependencies."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "README.md",
    "LICENSE",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    ".github/CODEOWNERS",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
    ".github/ISSUE_TEMPLATE/documentation.yml",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/repository-metadata.yml",
    ".github/workflows/ci.yml",
)

MARKDOWN_FILES = (
    "README.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
)

POLICY_FILES = (
    "README.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
)

ISSUE_FORMS = (
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
    ".github/ISSUE_TEMPLATE/documentation.yml",
)

LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
PLACEHOLDER_RE = re.compile(
    r"(?:\[INSERT[^\]]*\]|<INSERT[^>]*>|\bCHANGEME\b|\bPLACEHOLDER_CONTACT\b)",
    re.IGNORECASE,
)


def validate_required_files(errors: list[str]) -> None:
    for relative in REQUIRED_FILES:
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"missing required governance file: {relative}")
        elif path.stat().st_size == 0:
            errors.append(f"required governance file is empty: {relative}")


def validate_license(errors: list[str]) -> None:
    path = ROOT / "LICENSE"
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    if "Apache License" not in text or "Version 2.0, January 2004" not in text:
        errors.append("LICENSE must contain the Apache License 2.0 text")
    if "Copyright 2026 magic-alt contributors" not in text:
        errors.append("LICENSE is missing the project copyright notice")


def validate_codeowners(errors: list[str]) -> None:
    path = ROOT / ".github/CODEOWNERS"
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    if "* @magic-alt" not in text:
        errors.append("CODEOWNERS must define @magic-alt as the default owner")


def validate_issue_forms(errors: list[str]) -> None:
    for relative in ISSUE_FORMS:
        path = ROOT / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for key in ("name:", "description:", "body:"):
            if key not in text:
                errors.append(f"{relative} is missing required issue-form key {key!r}")

    config = ROOT / ".github/ISSUE_TEMPLATE/config.yml"
    if config.is_file():
        text = config.read_text(encoding="utf-8")
        if "blank_issues_enabled: false" not in text:
            errors.append("issue-template config must disable blank issues")
        if "/security/policy" not in text:
            errors.append("issue-template config must route security reports to the security policy")


def validate_repository_metadata(errors: list[str]) -> None:
    path = ROOT / ".github/repository-metadata.yml"
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    if "description:" not in text:
        errors.append("repository metadata is missing a description")
    required_topics = (
        "quantitative-finance",
        "algorithmic-trading",
        "quantconnect",
        "lean",
        "backtesting",
    )
    for topic in required_topics:
        if f"- {topic}" not in text:
            errors.append(f"repository metadata is missing required topic: {topic}")


def normalize_markdown_target(raw: str) -> str:
    target = raw.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    # Ignore an optional Markdown link title after a whitespace separator.
    if " \"" in target:
        target = target.split(" \"", 1)[0]
    if " '" in target:
        target = target.split(" '", 1)[0]
    return unquote(target)


def validate_markdown_links(errors: list[str]) -> None:
    schemes = ("http://", "https://", "mailto:", "tel:")
    root = ROOT.resolve()
    for relative in MARKDOWN_FILES:
        source = ROOT / relative
        if not source.is_file():
            continue
        text = source.read_text(encoding="utf-8")
        for match in LINK_RE.finditer(text):
            target = normalize_markdown_target(match.group(1))
            if not target or target.startswith("#") or target.startswith(schemes):
                continue
            file_target = target.split("#", 1)[0].split("?", 1)[0]
            if not file_target:
                continue
            resolved = (source.parent / file_target).resolve()
            try:
                resolved.relative_to(root)
            except ValueError:
                errors.append(f"{relative}: link escapes repository root: {target}")
                continue
            if not resolved.exists():
                errors.append(f"{relative}: broken relative link: {target}")


def validate_policy_claims(errors: list[str]) -> None:
    for relative in POLICY_FILES:
        path = ROOT / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        match = PLACEHOLDER_RE.search(text)
        if match:
            errors.append(f"{relative}: unresolved governance placeholder: {match.group(0)!r}")

    readme = ROOT / "README.md"
    if readme.is_file():
        text = readme.read_text(encoding="utf-8")
        required_claims = (
            "NOT CERTIFIED",
            "Live trading / P9 activation is disabled",
            "Apache License 2.0",
            "Artifact Contract v2",
        )
        for claim in required_claims:
            if claim not in text:
                errors.append(f"README.md must preserve current boundary claim: {claim!r}")

    contributing = ROOT / "CONTRIBUTING.md"
    if contributing.is_file():
        text = contributing.read_text(encoding="utf-8")
        for claim in ("CHANGELOG.md", "BROKER_WRITE", "LIVE_ACTIVATION"):
            if claim not in text:
                errors.append(f"CONTRIBUTING.md is missing required governance rule: {claim!r}")

    security = ROOT / "SECURITY.md"
    if security.is_file():
        text = security.read_text(encoding="utf-8")
        if "Do not open a public issue" not in text:
            errors.append("SECURITY.md must explicitly prohibit public vulnerability reports")


def main() -> int:
    errors: list[str] = []
    validate_required_files(errors)
    validate_license(errors)
    validate_codeowners(errors)
    validate_issue_forms(errors)
    validate_repository_metadata(errors)
    validate_markdown_links(errors)
    validate_policy_claims(errors)

    if errors:
        print("Open-source governance validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("Open-source governance validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
