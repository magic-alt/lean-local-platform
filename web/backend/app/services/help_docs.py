from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..core.config import PLATFORM_DIR
from ..core.errors import NotFoundError


DOCS_DIR = PLATFORM_DIR / "docs" / "help"


def _plain(markdown: str) -> str:
    return re.sub(r"[`#>*_|\[\]()]", " ", markdown)


@lru_cache(maxsize=1)
def articles() -> tuple[dict[str, Any], ...]:
    result = []
    for order, path in enumerate(sorted(DOCS_DIR.glob("*.md")), start=1):
        content = path.read_text(encoding="utf-8")
        title_match = re.search(r"^#\s+(.+)$", content, flags=re.MULTILINE)
        title = title_match.group(1).strip() if title_match else path.stem
        text = " ".join(_plain(content).split())
        result.append({"slug": path.stem, "title": title, "category": path.stem, "order": order, "content": content, "searchText": text})
    return tuple(result)


def list_articles(query: str | None = None) -> list[dict[str, Any]]:
    needle = str(query or "").strip().casefold()
    result = []
    for item in articles():
        haystack = f"{item['title']} {item['searchText']}".casefold()
        if needle and needle not in haystack:
            continue
        position = haystack.find(needle) if needle else 0
        raw = item["searchText"]
        start = max(0, position - 60)
        result.append({key: item[key] for key in ("slug", "title", "category", "order")} | {"snippet": raw[start:start + 180]})
    return result


def article(slug: str) -> dict[str, Any]:
    if not re.fullmatch(r"[a-z0-9-]+", slug):
        raise NotFoundError("Help article not found.")
    item = next((entry for entry in articles() if entry["slug"] == slug), None)
    if item is None:
        raise NotFoundError("Help article not found.")
    return {key: item[key] for key in ("slug", "title", "category", "order", "content")}
