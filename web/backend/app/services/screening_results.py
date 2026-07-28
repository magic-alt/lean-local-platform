from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .security_identity import canonical_security_symbol, resolve_security_identities


def enrich_screening_payload(
    payload: dict[str, Any],
    *,
    market: str = "china",
) -> dict[str, Any]:
    raw_items = [item for item in payload.get("items") or [] if isinstance(item, dict)]
    identities = resolve_security_identities(
        [item.get("symbol") for item in raw_items],
        market=market,
    )
    items = []
    for item in raw_items:
        symbol = canonical_security_symbol(item.get("symbol"), market)
        identity = identities.get(symbol) or {
            "symbol": symbol,
            "name": None,
            "display": symbol,
        }
        name = item.get("name") or identity.get("name")
        items.append({
            **item,
            "symbol": symbol,
            "name": name,
            "symbolDisplay": " ".join(value for value in (symbol, name) if value),
        })
    item_by_symbol = {item["symbol"]: item for item in items}
    summary = dict(payload.get("summary") or {})
    selected_symbols = [
        canonical_security_symbol(value, market)
        for value in summary.get("selected") or []
    ]
    qualified = sorted(
        (item for item in items if item.get("suitableToBuy")),
        key=lambda item: (-float(item.get("overallScore") or 0), item["symbol"]),
    )
    if not selected_symbols:
        selected_symbols = [
            canonical_security_symbol(item.get("symbol"), market)
            for item in payload.get("selected") or []
            if isinstance(item, dict)
        ]
    summary.update({
        "schemaVersion": max(2, int(summary.get("schemaVersion") or 1)),
        "mode": "screening",
        "tradeSimulation": False,
        "evaluated": len(items),
        "qualified": len(qualified),
        "qualifiedSymbols": [item["symbol"] for item in qualified],
        "selected": selected_symbols,
    })
    return {
        **payload,
        "schemaVersion": 2,
        "sourceSchemaVersion": int(payload.get("schemaVersion") or 1),
        "mode": "screening",
        "tradeSimulation": False,
        "summary": summary,
        "items": items,
        "qualified": qualified,
        "selected": [
            item_by_symbol[symbol]
            for symbol in selected_symbols
            if symbol in item_by_symbol
        ],
    }


def load_screening_result(path: Path, *, market: str = "china") -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Screening result must be a JSON object.")
    return enrich_screening_payload(payload, market=market)


def enrich_screening_file(path: Path, *, market: str = "china") -> dict[str, Any]:
    payload = load_screening_result(path, market=market)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload
