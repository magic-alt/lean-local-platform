#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = ROOT / "docs"
CATALOG_PATH = DOCS_ROOT / "help" / "catalog.json"
LINK_RE = re.compile(r"!?\[[^]]*\]\(([^)]+)\)")
SEMANTIC_RULES = {
    "unpinned LEAN image": re.compile(r"quantconnect/lean:latest", re.IGNORECASE),
    "developer-specific absolute path": re.compile(r"/Users/kaermax", re.IGNORECASE),
    "retired MySQL container": re.compile(r"lean-platform-mysql|docker compose[^\n]*(?:\bmysql\b)", re.IGNORECASE),
    "retired Redis container": re.compile(r"docker compose[^\n]*(?:\bredis\b)", re.IGNORECASE),
    "legacy MySQL environment": re.compile(r"\bLEAN_MYSQL_[A-Z0-9_]+\b"),
    "legacy Redis environment": re.compile(r"\bREDIS_URL\b"),
}
HISTORICAL_CONTEXT = re.compile(
    r"historical|history|legacy|retired|removed|reject(?:ed)?|deprecated|旧|历史|已移除|拒绝|禁用|不再",
    re.IGNORECASE,
)


def semantic_errors(path: Path, content: str) -> list[str]:
    errors: list[str] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        if HISTORICAL_CONTEXT.search(line):
            continue
        for label, pattern in SEMANTIC_RULES.items():
            if pattern.search(line):
                errors.append(
                    f"Stale current-doc term ({label}) in {path.relative_to(ROOT)}:{line_number}"
                )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate in-app help document links and assets.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    sources: dict[Path, str] = {}
    semantic_sources: set[Path] = set()
    errors: list[str] = []
    for item in catalog:
        source = (DOCS_ROOT / item["source"]).resolve()
        if not source.is_relative_to(DOCS_ROOT.resolve()) or not source.is_file():
            errors.append(f"Missing or unsafe source for {item['slug']}: {item['source']}")
            continue
        if source in sources:
            errors.append(f"Duplicate source: {item['source']}")
        sources[source] = item["slug"]
        if item.get("status", "current") != "historical":
            semantic_sources.add(source)
    for source, slug in sources.items():
        content = source.read_text(encoding="utf-8")
        if source in semantic_sources:
            errors.extend(semantic_errors(source, content))
        for match in LINK_RE.finditer(content):
            target = match.group(1).strip().split("#", 1)[0]
            if not target or re.match(r"^(?:https?://|mailto:|/)", target):
                continue
            resolved = (source.parent / target).resolve()
            is_image = match.group(0).startswith("!")
            if is_image:
                if not resolved.is_relative_to((DOCS_ROOT / "help" / "assets").resolve()) or not resolved.is_file():
                    errors.append(f"Broken help image in {slug}: {target}")
            elif target.lower().endswith(".md") and resolved not in sources:
                errors.append(f"Uncatalogued help link in {slug}: {target}")
    for source in (ROOT / "AGENTS.md", ROOT / "README.md"):
        errors.extend(semantic_errors(source, source.read_text(encoding="utf-8")))
    result = {"ok": not errors, "articles": len(sources), "errors": errors}
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"Checked {len(sources)} help articles")
        for error in errors:
            print(f"- {error}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
