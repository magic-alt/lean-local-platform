from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from ..core.config import PLATFORM_DIR
from ..core.errors import NotFoundError
from .projects import create_project, update_project
from .settings import get_settings


CATALOG_PATH = PLATFORM_DIR / "examples" / "catalog.json"
# Research execution lives in qlib-platform. Keep this catalog limited to
# executable LEAN control-plane examples.
KINDS = {"backtest", "optimization"}


@lru_cache(maxsize=1)
def _catalog() -> tuple[dict[str, Any], ...]:
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Example catalog must be a JSON array.")
    seen: set[tuple[str, str]] = set()
    items: list[dict[str, Any]] = []
    for raw in payload:
        item = dict(raw)
        kind = str(item.get("kind") or "").strip().lower()
        key = str(item.get("key") or "").strip()
        identity = (kind, key)
        if kind not in KINDS or not key or identity in seen:
            raise ValueError(f"Invalid or duplicate example catalog entry: {identity}")
        seen.add(identity)
        item.setdefault("version", 1)
        item.setdefault("tags", [])
        item.setdefault("defaults", {})
        items.append(item)
    return tuple(items)


def list_examples(kind: str | None = None, query: str | None = None) -> list[dict[str, Any]]:
    normalized_kind = str(kind or "").strip().lower()
    if normalized_kind and normalized_kind not in KINDS:
        return []
    needle = str(query or "").strip().casefold()
    result = []
    for item in _catalog():
        if normalized_kind and item["kind"] != normalized_kind:
            continue
        haystack = " ".join(
            [str(item.get("name") or ""), str(item.get("description") or ""), *map(str, item.get("tags") or [])]
        ).casefold()
        if needle and needle not in haystack:
            continue
        result.append(dict(item))
    return result


def get_example(kind: str, key: str) -> dict[str, Any]:
    normalized = str(kind).strip().lower()
    if normalized not in KINDS:
        raise NotFoundError("Research examples are retired here; use qlib-platform.")
    item = next((candidate for candidate in _catalog() if candidate["kind"] == normalized and candidate["key"] == key), None)
    if item is None:
        raise NotFoundError("Example not found.")
    return dict(item)


def instantiate_example(
    kind: str,
    key: str,
    *,
    name: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    example = get_example(kind, key)
    defaults = {**(example.get("defaults") or {}), **(overrides or {})}
    settings = get_settings()
    market = str(defaults.get("market") or settings["defaultMarket"])
    project = create_project(
        name or str(example["name"]),
        "Python",
        template_key=str(example.get("templateKey") or "blank"),
        asset_class=str(defaults.get("assetClass") or settings["defaultAssetClass"]),
        market=market,
        venue=str(defaults.get("venue") or market),
        resolution=str(defaults.get("resolution") or settings["defaultResolution"]),
        data_type=str(defaults.get("dataType") or settings["defaultDataType"]),
        parameters=dict(defaults.get("parameters") or {}),
    )
    project = update_project(
        project["id"],
        config_updates={
            "exampleKey": example["key"],
            "exampleKind": example["kind"],
            "exampleVersion": example["version"],
            "exampleDefaults": defaults,
        },
    )
    route = "/backtests" if example["kind"] == "backtest" else "/optimization"
    return {
        "example": example,
        "project": project,
        "launch": {"route": route, "defaults": defaults},
    }
