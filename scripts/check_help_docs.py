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


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate in-app help document links and assets.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    sources: dict[Path, str] = {}
    errors: list[str] = []
    for item in catalog:
        source = (DOCS_ROOT / item["source"]).resolve()
        if not source.is_relative_to(DOCS_ROOT.resolve()) or not source.is_file():
            errors.append(f"Missing or unsafe source for {item['slug']}: {item['source']}")
            continue
        if source in sources:
            errors.append(f"Duplicate source: {item['source']}")
        sources[source] = item["slug"]
    for source, slug in sources.items():
        content = source.read_text(encoding="utf-8")
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
