from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any

from ..core.config import PLATFORM_DIR
from ..core.errors import NotFoundError


DOCS_ROOT = (PLATFORM_DIR / "docs").resolve()
DOCS_DIR = DOCS_ROOT / "help"
CATALOG_PATH = DOCS_DIR / "catalog.json"
ASSETS_DIR = (DOCS_DIR / "assets").resolve()
ALLOWED_ASSET_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}

_CACHE_LOCK = threading.Lock()
_CACHE_SIGNATURE: tuple[Any, ...] | None = None
_CACHE_ARTICLES: tuple[dict[str, Any], ...] = ()


def _plain(markdown: str) -> str:
    value = re.sub(r"```.*?```", " ", markdown, flags=re.DOTALL)
    value = re.sub(r"!\[([^]]*)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"[`#>*_|~\[\]()]", " ", value)


def _resolve_source(source: str) -> Path:
    path = (DOCS_ROOT / source).resolve()
    if not path.is_relative_to(DOCS_ROOT) or path.suffix.lower() != ".md":
        raise ValueError(f"Help document source is outside docs/: {source}")
    return path


def _load_catalog() -> tuple[list[dict[str, Any]], str]:
    raw = CATALOG_PATH.read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError("Help catalog must be a JSON array.")
    return [dict(item) for item in payload], raw


def _signature(entries: list[dict[str, Any]], catalog_raw: str) -> tuple[Any, ...]:
    files: list[tuple[str, int, int]] = []
    for entry in entries:
        path = _resolve_source(str(entry.get("source") or ""))
        stat = path.stat()
        files.append((str(path), stat.st_mtime_ns, stat.st_size))
    return catalog_raw, tuple(files)


def _build_articles(entries: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    seen_slugs: set[str] = set()
    seen_sources: set[Path] = set()
    result: list[dict[str, Any]] = []
    for entry in entries:
        slug = str(entry.get("slug") or "").strip()
        if not re.fullmatch(r"[a-z0-9-]+", slug) or slug in seen_slugs:
            raise ValueError(f"Invalid or duplicate help slug: {slug}")
        path = _resolve_source(str(entry.get("source") or ""))
        if path in seen_sources or not path.is_file():
            raise ValueError(f"Missing or duplicate help source: {path}")
        group = str(entry.get("group") or "guide")
        status = str(entry.get("status") or "current")
        if group not in {"guide", "reference"} or status not in {"current", "historical"}:
            raise ValueError(f"Invalid help metadata for {slug}")
        content = path.read_text(encoding="utf-8")
        title_match = re.search(r"^#\s+(.+)$", content, flags=re.MULTILINE)
        title = title_match.group(1).strip() if title_match else slug
        text = " ".join(_plain(content).split())
        seen_slugs.add(slug)
        seen_sources.add(path)
        result.append(
            {
                "slug": slug,
                "title": title,
                "group": group,
                "category": str(entry.get("category") or "general"),
                "order": int(entry.get("order") or len(result) + 1),
                "summary": str(entry.get("summary") or "").strip(),
                "status": status,
                "content": content,
                "searchText": text,
            }
        )
    return tuple(sorted(result, key=lambda item: (item["group"] != "guide", item["order"], item["title"])))


def articles() -> tuple[dict[str, Any], ...]:
    global _CACHE_ARTICLES, _CACHE_SIGNATURE
    entries, catalog_raw = _load_catalog()
    signature = _signature(entries, catalog_raw)
    with _CACHE_LOCK:
        if signature != _CACHE_SIGNATURE:
            _CACHE_ARTICLES = _build_articles(entries)
            _CACHE_SIGNATURE = signature
        return _CACHE_ARTICLES


def _summary(item: dict[str, Any], snippet: str) -> dict[str, Any]:
    return {key: item[key] for key in ("slug", "title", "group", "category", "order", "summary", "status")} | {
        "snippet": snippet
    }


def list_articles(query: str | None = None) -> list[dict[str, Any]]:
    tokens = [token for token in str(query or "").strip().casefold().split() if token]
    result = []
    for item in articles():
        raw = f"{item['title']} {item['summary']} {item['searchText']}"
        haystack = raw.casefold()
        if tokens and not all(token in haystack for token in tokens):
            continue
        position = min((haystack.find(token) for token in tokens), default=0)
        start = max(0, position - 70)
        snippet = raw[start : start + 220].strip()
        result.append(_summary(item, snippet))
    return result


def article(slug: str) -> dict[str, Any]:
    if not re.fullmatch(r"[a-z0-9-]+", slug):
        raise NotFoundError("Help article not found.")
    item = next((entry for entry in articles() if entry["slug"] == slug), None)
    if item is None:
        raise NotFoundError("Help article not found.")
    return {key: item[key] for key in ("slug", "title", "group", "category", "order", "summary", "status", "content")}


def asset(asset_path: str) -> Path:
    path = (ASSETS_DIR / asset_path).resolve()
    if (
        not path.is_relative_to(ASSETS_DIR)
        or path.suffix.lower() not in ALLOWED_ASSET_SUFFIXES
        or not path.is_file()
    ):
        raise NotFoundError("Help asset not found.")
    return path
