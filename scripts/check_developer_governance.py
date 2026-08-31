#!/usr/bin/env python3
"""Validate repository-scoped agent, Codex, hook, and GitHub developer controls."""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SKILLS = {
    "broker-gateway-change", "ci-validation", "data-release-change",
    "lean-validation-change", "paper-execution-change", "qlib-handoff-review",
    "repo-audit", "repository-governance-review",
}
REQUIRED_FILES = (
    "AGENTS.md", ".agents/skills/README.md",
    ".agents/skills/repository-governance-review/SKILL.md",
    ".codex/README.md", ".codex/config.toml", ".codex/rules/safety.rules",
    ".codex/agents/repository-governance-reviewer.toml",
    ".githooks/README.md", ".githooks/pre-commit", ".githooks/commit-msg",
    ".github/README.md", ".github/CODEOWNERS", ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/workflows/ci.yml",
)
FRONT_MATTER_RE = re.compile(r"\A---\n(?P<meta>.*?)\n---\n", re.DOTALL)
FIELD_RE = re.compile(r"^(?P<key>[A-Za-z0-9_-]+):\s*(?P<value>.+?)\s*$")


def validate_required_files(errors: list[str]) -> None:
    for relative in REQUIRED_FILES:
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"missing developer-governance file: {relative}")
        elif path.stat().st_size == 0:
            errors.append(f"developer-governance file is empty: {relative}")


def parse_skill(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    match = FRONT_MATTER_RE.match(text)
    if not match:
        raise ValueError("missing YAML front matter delimited by ---")
    values: dict[str, str] = {}
    for line in match.group("meta").splitlines():
        field = FIELD_RE.match(line)
        if field:
            values[field.group("key")] = field.group("value").strip().strip("\"'")
    return values


def validate_skills(errors: list[str]) -> None:
    skills_root = ROOT / ".agents/skills"
    discovered: dict[str, Path] = {}
    if not skills_root.is_dir():
        return
    for skill_dir in sorted(p for p in skills_root.iterdir() if p.is_dir()):
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            errors.append(f"skill directory is missing SKILL.md: {skill_dir.relative_to(ROOT)}")
            continue
        try:
            meta = parse_skill(skill_file)
        except ValueError as exc:
            errors.append(f"{skill_file.relative_to(ROOT)}: {exc}")
            continue
        name = meta.get("name", "")
        description = meta.get("description", "")
        if not name:
            errors.append(f"{skill_file.relative_to(ROOT)}: missing front-matter name")
            continue
        if name != skill_dir.name:
            errors.append(f"{skill_file.relative_to(ROOT)}: name {name!r} must match directory {skill_dir.name!r}")
        if name in discovered:
            errors.append(f"duplicate repository skill name: {name}")
        discovered[name] = skill_file
        if len(description) < 40:
            errors.append(f"{skill_file.relative_to(ROOT)}: description is too vague for reliable routing")
        if not re.search(r"^#\s+\S", skill_file.read_text(encoding="utf-8"), re.MULTILINE):
            errors.append(f"{skill_file.relative_to(ROOT)}: skill body needs a top-level heading")
    for name in sorted(EXPECTED_SKILLS - set(discovered)):
        errors.append(f"expected repository skill is missing: {name}")
    for name in sorted(set(discovered) - EXPECTED_SKILLS):
        errors.append(f"unexpected repository skill is not cataloged: {name}")
    index = ROOT / ".agents/skills/README.md"
    if index.is_file():
        text = index.read_text(encoding="utf-8")
        for name in sorted(EXPECTED_SKILLS):
            if f"`{name}`" not in text:
                errors.append(f"skills README is missing catalog entry: {name}")


def load_toml(relative: str, errors: list[str]) -> dict[str, Any] | None:
    path = ROOT / relative
    if not path.is_file():
        return None
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        errors.append(f"{relative}: invalid TOML: {exc}")
        return None


def validate_codex(errors: list[str]) -> None:
    config = load_toml(".codex/config.toml", errors)
    if config is not None:
        for key, value in {
            "approval_policy": "on-request", "approvals_reviewer": "user",
            "sandbox_mode": "workspace-write", "allow_login_shell": False,
        }.items():
            if config.get(key) != value:
                errors.append(f".codex/config.toml: {key} must be {value!r}")
        if (config.get("sandbox_workspace_write") or {}).get("network_access") is not False:
            errors.append(".codex/config.toml: workspace-write network_access must remain false")
        if (config.get("shell_environment_policy") or {}).get("ignore_default_excludes") is not False:
            errors.append(".codex/config.toml: automatic secret-name environment exclusions must be enabled")
        agents = config.get("agents") or {}
        threads = agents.get("max_concurrent_threads_per_session")
        if agents.get("enabled") is not True or agents.get("interrupt_message") is not True:
            errors.append(".codex/config.toml: subagents must remain explicitly enabled with interruption context")
        if not isinstance(threads, int) or not 1 <= threads <= 4:
            errors.append(".codex/config.toml: subagent concurrency must remain between 1 and 4")

    names: set[str] = set()
    for path in sorted((ROOT / ".codex/agents").glob("*.toml")):
        payload = load_toml(str(path.relative_to(ROOT)), errors)
        if payload is None:
            continue
        for field in ("name", "description", "developer_instructions"):
            if not isinstance(payload.get(field), str) or not payload[field].strip():
                errors.append(f"{path.relative_to(ROOT)}: missing non-empty {field}")
        name = payload.get("name")
        if isinstance(name, str):
            if name in names:
                errors.append(f"duplicate Codex agent name: {name}")
            names.add(name)
        if payload.get("sandbox_mode") != "read-only":
            errors.append(f"{path.relative_to(ROOT)}: reviewer/explorer must use read-only sandbox")
        if "read-only" not in str(payload.get("developer_instructions", "")).lower():
            errors.append(f"{path.relative_to(ROOT)}: instructions must explicitly preserve read-only behavior")
    if "repository_governance_reviewer" not in names:
        errors.append(".codex/agents is missing repository_governance_reviewer")

    rules = ROOT / ".codex/rules/safety.rules"
    if rules.is_file():
        text = rules.read_text(encoding="utf-8")
        for fragment in (
            'pattern = ["git", "push", "--force"]', 'pattern = ["git", "reset", "--hard"]',
            'pattern = ["docker", "volume", "rm"]', 'pattern = ["docker", "volume", "prune"]',
            'pattern = ["rm", "-rf"]', 'pattern = ["gh", "repo", "delete"]',
            "match = [", "not_match = [",
        ):
            if fragment not in text:
                errors.append(f"Codex safety rules are missing guard/test: {fragment}")


def git_file_mode(relative: str) -> str | None:
    completed = subprocess.run(["git", "ls-files", "--stage", "--", relative], cwd=ROOT, check=True, capture_output=True, text=True)
    line = completed.stdout.strip()
    return line.split(maxsplit=1)[0] if line else None


def validate_hooks_and_github(errors: list[str]) -> None:
    for relative, fragments in {
        ".githooks/pre-commit": ("check_repository_hygiene.py", "check_developer_governance.py"),
        ".githooks/commit-msg": ("check_changelog.py",),
    }.items():
        path = ROOT / relative
        if not path.is_file():
            continue
        mode = git_file_mode(relative)
        if mode is not None and mode != "100755":
            errors.append(f"{relative}: tracked Git mode must be 100755, got {mode}")
        text = path.read_text(encoding="utf-8")
        for fragment in fragments:
            if fragment not in text:
                errors.append(f"{relative}: missing expected check {fragment}")

    codeowners = ROOT / ".github/CODEOWNERS"
    if codeowners.is_file():
        text = codeowners.read_text(encoding="utf-8")
        for owned in ("/AGENTS.md", "/.agents/", "/.codex/", "/.githooks/"):
            if owned not in text:
                errors.append(f"CODEOWNERS must explicitly own: {owned}")
    template = ROOT / ".github/PULL_REQUEST_TEMPLATE.md"
    if template.is_file():
        text = template.read_text(encoding="utf-8")
        for claim in ("Developer automation / repository governance", "check_developer_governance.py"):
            if claim not in text:
                errors.append(f"PR template is missing developer-governance requirement: {claim}")
    ci = ROOT / ".github/workflows/ci.yml"
    if ci.is_file() and "python scripts/check_developer_governance.py" not in ci.read_text(encoding="utf-8"):
        errors.append("CI Governance job must run check_developer_governance.py")


def validate_docs(errors: list[str]) -> None:
    agents = ROOT / "AGENTS.md"
    if agents.is_file():
        text = agents.read_text(encoding="utf-8")
        for claim in (".agents/skills/", ".codex/config.toml", ".githooks/", ".github/", "check_developer_governance.py", "behaviorally", "read-only"):
            if claim not in text:
                errors.append(f"AGENTS.md is missing developer-control-plane guidance: {claim}")
    codex = ROOT / ".codex/README.md"
    if codex.is_file():
        text = codex.read_text(encoding="utf-8")
        for url in (
            "https://developers.openai.com/codex/config-reference/",
            "https://developers.openai.com/codex/rules/",
            "https://developers.openai.com/codex/subagents/",
            "https://developers.openai.com/codex/skills/",
        ):
            if url not in text:
                errors.append(f".codex/README.md is missing upstream reference: {url}")


def main() -> int:
    errors: list[str] = []
    validate_required_files(errors)
    validate_skills(errors)
    validate_codex(errors)
    validate_hooks_and_github(errors)
    validate_docs(errors)
    if errors:
        print("Developer governance validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Developer governance validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
