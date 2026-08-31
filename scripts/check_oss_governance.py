#!/usr/bin/env python3
"""Validate open-source and repository-governance files without third-party dependencies."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "README.md",
    "VERSION",
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
    ".github/dependabot.yml",
    ".github/release.yml",
    ".github/repository-metadata.yml",
    ".github/repository-policy.json",
    ".github/workflows/ci.yml",
    ".github/workflows/codeql.yml",
    ".github/workflows/dependency-review.yml",
    ".github/workflows/release.yml",
    "docs/repository-governance.md",
    "docs/releasing.md",
    "scripts/check_release_version.py",
    "scripts/audit_repository_settings.py",
)

MARKDOWN_FILES = (
    "README.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "docs/repository-governance.md",
    "docs/releasing.md",
)

POLICY_FILES = (
    "README.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
    "docs/repository-governance.md",
    "docs/releasing.md",
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
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
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


def validate_version(errors: list[str]) -> None:
    path = ROOT / "VERSION"
    if not path.is_file():
        return
    version = path.read_text(encoding="utf-8").strip()
    if not SEMVER_RE.fullmatch(version):
        errors.append(f"VERSION must be valid SemVer, got {version!r}")


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


def validate_repository_policy(errors: list[str]) -> None:
    path = ROOT / ".github/repository-policy.json"
    if not path.is_file():
        return
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"repository policy is invalid JSON: {exc}")
        return
    if policy.get("schemaVersion") != 1:
        errors.append("repository policy must use schemaVersion 1")
    rulesets = policy.get("rulesets") or []
    by_name = {item.get("name"): item for item in rulesets if isinstance(item, dict)}
    main = by_name.get("Protect main")
    if not main:
        errors.append("repository policy is missing the Protect main ruleset")
    else:
        checks = main.get("required_status_checks") or []
        for check in ("Governance", "Dependency Review"):
            if check not in checks:
                errors.append(f"Protect main must require status check: {check}")
        if main.get("required_approving_reviews") != 0:
            errors.append("single-maintainer baseline must use 0 required approvals")
        if not main.get("strict_status_checks"):
            errors.append("Protect main must require strict/up-to-date status checks")
    tags = by_name.get("Protect release tags")
    if not tags:
        errors.append("repository policy is missing the Protect release tags ruleset")


def validate_dependency_security(errors: list[str]) -> None:
    dependabot = ROOT / ".github/dependabot.yml"
    if dependabot.is_file():
        text = dependabot.read_text(encoding="utf-8")
        for ecosystem in ("github-actions", "npm", "pip", "docker", "docker-compose"):
            if f"package-ecosystem: {ecosystem}" not in text:
                errors.append(f"Dependabot is missing ecosystem: {ecosystem}")

    review = ROOT / ".github/workflows/dependency-review.yml"
    if review.is_file():
        text = review.read_text(encoding="utf-8")
        if "actions/dependency-review-action@v4" not in text:
            errors.append("Dependency Review must use actions/dependency-review-action@v4")
        if "fail-on-severity: high" not in text:
            errors.append("Dependency Review must fail on high-or-greater vulnerabilities")
        if "name: Dependency Review" not in text:
            errors.append("Dependency Review check name must remain stable for Ruleset use")

    codeql = ROOT / ".github/workflows/codeql.yml"
    if codeql.is_file():
        text = codeql.read_text(encoding="utf-8")
        for claim in (
            "github/codeql-action/init@v4",
            "github/codeql-action/analyze@v4",
            "python",
            "javascript-typescript",
            "security-events: write",
        ):
            if claim not in text:
                errors.append(f"CodeQL workflow is missing required configuration: {claim}")


def validate_release_policy(errors: list[str]) -> None:
    release = ROOT / ".github/workflows/release.yml"
    if release.is_file():
        text = release.read_text(encoding="utf-8")
        for claim in (
            "workflow_dispatch:",
            "check_release_version.py",
            "--require-changelog",
            "--draft",
            "--verify-tag",
        ):
            if claim not in text:
                errors.append(f"Release workflow is missing required safety gate: {claim}")

    docs = ROOT / "docs/releasing.md"
    if docs.is_file():
        text = docs.read_text(encoding="utf-8")
        for claim in ("Semantic Versioning", "production certification", "VERSION", "draft"):
            if claim not in text:
                errors.append(f"release documentation is missing required policy claim: {claim}")


def normalize_markdown_target(raw: str) -> str:
    target = raw.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
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
    validate_version(errors)
    validate_codeowners(errors)
    validate_issue_forms(errors)
    validate_repository_metadata(errors)
    validate_repository_policy(errors)
    validate_dependency_security(errors)
    validate_release_policy(errors)
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
