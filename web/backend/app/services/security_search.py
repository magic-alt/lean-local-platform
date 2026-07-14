from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from ..db import db, rows_to_dicts
from ..lean_engine.data_paths import list_local_symbols
from ..lean_engine.symbols import MARKET_CONFIG, market_key, normalize_symbol

try:  # Optional at import time so older local environments keep working.
    from pypinyin import Style, lazy_pinyin
except ImportError:  # pragma: no cover - only before dependencies are refreshed.
    Style = None
    lazy_pinyin = None


MARKET_LABELS = {"china": "A股", "hongkong": "H股", "usa": "美股"}


def _search_key(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[\s._-]+", "", text)


def _pinyin_keys(value: str) -> tuple[str, str]:
    if not value or lazy_pinyin is None or Style is None:
        return "", ""
    full = "".join(lazy_pinyin(value)).casefold()
    initials = "".join(lazy_pinyin(value, style=Style.FIRST_LETTER)).casefold()
    return _search_key(full), _search_key(initials)


def _metadata_aliases(value: Any) -> list[str]:
    if not value:
        return []
    try:
        metadata = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        return []
    if not isinstance(metadata, dict):
        return []
    aliases: list[str] = []
    for key in ("aliases", "alias", "name_en", "english_name", "short_name"):
        item = metadata.get(key)
        if isinstance(item, list):
            aliases.extend(str(part) for part in item if part)
        elif item:
            aliases.append(str(item))
    return aliases


def _code_variants(symbol: str, market: str, exchange: str | None) -> list[str]:
    value = symbol.upper()
    variants = [value]
    if market == "china" and value.isdigit():
        suffix = "SH" if (exchange or "").upper() in {"SSE", "SH", "XSHG"} or value.startswith(("5", "6", "9")) else "SZ"
        variants.extend((f"{suffix}{value}", f"{value}.{suffix}"))
    elif market == "hongkong" and value.isdigit():
        padded = value.zfill(5)
        variants.extend((f"HK{padded}", f"{padded}.HK"))
    return list(dict.fromkeys(variants))


def _match(query: str, candidate: dict[str, Any]) -> tuple[int, str, str] | None:
    code_keys = [_search_key(item) for item in _code_variants(candidate["symbol"], candidate["market"], candidate.get("exchange"))]
    name_key = _search_key(candidate.get("name"))
    alias_keys = [_search_key(item) for item in candidate.get("aliases", [])]
    pinyin_full, pinyin_abbr = _pinyin_keys(str(candidate.get("name") or ""))

    for values, score, field in (
        (code_keys, 100, "code"),
        ([name_key], 98, "name"),
        (alias_keys, 97, "alias"),
        ([pinyin_abbr, pinyin_full], 96, "pinyin"),
    ):
        if query in {value for value in values if value}:
            return score, "exact", field
    for values, score, field in (
        (code_keys, 80, "code"),
        ([name_key], 79, "name"),
        ([pinyin_abbr, pinyin_full], 78, "pinyin"),
        (alias_keys, 77, "alias"),
    ):
        if any(value.startswith(query) for value in values if value):
            return score, "prefix", field
    for values, score, field in (
        (code_keys, 60, "code"),
        ([name_key], 59, "name"),
        ([pinyin_full, pinyin_abbr], 58, "pinyin"),
        (alias_keys, 57, "alias"),
    ):
        if any(query in value for value in values if value):
            return score, "contains", field
    return None


def _database_candidates(markets: list[str]) -> list[dict[str, Any]]:
    placeholders = ",".join("?" for _ in markets)
    with db() as connection:
        instruments = rows_to_dicts(connection.execute(
            f"""
            select symbol, name, market, exchange, metadata_json, status
            from instruments
            where asset_class = 'equity' and market in ({placeholders})
            """,
            markets,
        ).fetchall())
        securities = rows_to_dicts(connection.execute(
            f"""
            select symbol, name, market, exchange, null as metadata_json, status
            from securities
            where market in ({placeholders})
            """,
            markets,
        ).fetchall())

    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for item in [*securities, *instruments]:
        item_market = market_key(str(item.get("market") or "china"))
        symbol = str(item.get("symbol") or "").upper()
        if not symbol:
            continue
        key = (item_market, symbol)
        previous = merged.get(key, {})
        merged[key] = {
            "symbol": symbol,
            "name": item.get("name") or previous.get("name") or symbol,
            "market": item_market,
            "exchange": item.get("exchange") or previous.get("exchange"),
            "status": item.get("status") or previous.get("status"),
            "aliases": list(dict.fromkeys([*previous.get("aliases", []), *_metadata_aliases(item.get("metadata") or item.get("metadata_json"))])),
        }
    return list(merged.values())


def search_securities(keyword: str = "", market: str = "all", limit: int = 50) -> dict[str, Any]:
    market_value = str(market or "all").strip().lower()
    markets = list(MARKET_CONFIG) if market_value in {"", "all", "global"} else [market_key(market_value)]
    local_by_market = {item_market: set(list_local_symbols(item_market)) for item_market in markets}
    candidates = _database_candidates(markets)
    known = {(item["market"], item["symbol"]) for item in candidates}
    for item_market, symbols in local_by_market.items():
        for symbol in symbols:
            if (item_market, symbol) not in known:
                candidates.append({"symbol": symbol, "name": symbol, "market": item_market, "exchange": None, "status": "local", "aliases": []})

    query = _search_key(keyword)
    results: list[dict[str, Any]] = []
    for candidate in candidates:
        matched = _match(query, candidate) if query else (1, "browse", "none")
        if not matched:
            continue
        score, match_type, match_field = matched
        has_local_data = candidate["symbol"] in local_by_market[candidate["market"]]
        results.append({
            "symbol": candidate["symbol"],
            "name": candidate["name"],
            "market": candidate["market"],
            "marketLabel": MARKET_LABELS[candidate["market"]],
            "exchange": candidate.get("exchange"),
            "status": candidate.get("status"),
            "hasLocalData": has_local_data,
            "matchType": match_type,
            "matchField": match_field,
            "score": score + (2 if has_local_data else 0),
        })

    results.sort(key=lambda item: (-item["score"], item["market"], item["symbol"]))
    bounded_limit = max(1, min(int(limit), 100))
    selected = results[:bounded_limit]

    if query and len(markets) == 1 and not any(item["matchField"] == "code" and item["matchType"] == "exact" for item in selected):
        try:
            normalized = normalize_symbol(keyword, markets[0]).upper()
        except Exception:
            normalized = ""
        if normalized and normalized == str(keyword).strip().upper() and (markets[0], normalized) not in known:
            selected.insert(0, {
                "symbol": normalized,
                "name": normalized,
                "market": markets[0],
                "marketLabel": MARKET_LABELS[markets[0]],
                "exchange": None,
                "status": "manual",
                "hasLocalData": normalized in local_by_market[markets[0]],
                "matchType": "exact",
                "matchField": "code",
                "score": 100,
            })
            selected = selected[:bounded_limit]

    return {"items": selected, "count": len(selected), "query": keyword, "markets": markets}
