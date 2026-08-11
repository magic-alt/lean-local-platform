from __future__ import annotations

import hashlib
import json
from typing import Any

from ..db import db, rows_to_dicts
from ..domain.data_scope import DataScope
from .source_gate import (
    PRIMARY_DATA_SOURCE,
    require_source_allowed,
    resolve_source_chain,
    source_certification,
)


BAR_FIELDS = {
    "symbol",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "settle",
    "volume",
    "amount",
    "turnover_rate",
    "open_interest",
    "prev_close",
    "pct_change",
    "source",
}


def normalize_scope(scope: DataScope | dict[str, Any]) -> dict[str, Any]:
    model = scope if isinstance(scope, DataScope) else DataScope.model_validate(scope)
    payload = model.model_dump(mode="json")
    asset = payload["asset"]
    selection = payload["selection"]
    time = payload["time"]
    provider = payload["provider"]
    asset["assetClass"] = asset["assetClass"].strip().lower()
    asset["market"] = asset["market"].strip().lower()
    asset["venue"] = (asset.get("venue") or asset["market"]).strip().lower()
    asset["resolution"] = asset["resolution"].strip().lower()
    asset["dataType"] = asset["dataType"].strip().lower()
    selection["values"] = sorted(
        {str(value).strip().upper() for value in selection["values"] if str(value).strip()}
    )
    payload["price"]["adjust"] = payload["price"]["adjust"].strip().lower() or "raw"
    provider["source"] = provider["source"].strip().lower() or PRIMARY_DATA_SOURCE
    return payload


def scope_hash(scope: DataScope | dict[str, Any]) -> str:
    normalized = normalize_scope(scope)
    encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _sources(scope: dict[str, Any]) -> list[str]:
    provider = scope["provider"]
    source = require_source_allowed(
        provider["source"],
        allow_research_source=bool(provider["allowResearchSource"]),
    )
    if provider["mode"] == "strict":
        return [source]
    candidates = resolve_source_chain(
        source,
        start_date=scope["time"].get("startDate"),
        end_date=scope["time"].get("endDate"),
    )
    allowed = []
    for candidate in candidates:
        try:
            allowed.append(
                require_source_allowed(
                    candidate,
                    allow_research_source=bool(provider["allowResearchSource"]),
                )
            )
        except ValueError:
            continue
    return allowed or [source]


def _coverage_for_source(scope: dict[str, Any], source: str) -> dict[str, Any]:
    asset = scope["asset"]
    selection = scope["selection"]
    time = scope["time"]
    clauses = [
        "asset_class = ?",
        "market = ?",
        "coalesce(venue, market) = ?",
        "resolution = ?",
        "data_type = ?",
        "adjust = ?",
        "source = ?",
    ]
    params: list[Any] = [
        asset["assetClass"],
        asset["market"],
        asset["venue"],
        asset["resolution"],
        asset["dataType"],
        scope["price"]["adjust"],
        source,
    ]
    if selection["type"] in {"symbols", "products"} and selection["values"]:
        clauses.append(f"symbol in ({','.join('?' for _ in selection['values'])})")
        params.extend(selection["values"])
    if time.get("startDate"):
        clauses.append("trade_date >= ?")
        params.append(time["startDate"])
    if time.get("endDate"):
        clauses.append("trade_date <= ?")
        params.append(time["endDate"])
    with db() as connection:
        row = connection.execute(
            f"""
            select count(*) as rows, count(distinct symbol) as symbols,
                   min(trade_date) as first_date, max(trade_date) as last_date
            from market_daily_bars where {' and '.join(clauses)}
            """,
            params,
        ).fetchone()
    return dict(row) if row else {"rows": 0, "symbols": 0, "first_date": None, "last_date": None}


def resolve(scope: DataScope | dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_scope(scope)
    attempts = []
    selected = None
    coverage: dict[str, Any] = {}
    for source in _sources(normalized):
        current = _coverage_for_source(normalized, source)
        attempts.append({"source": source, "rows": int(current.get("rows") or 0)})
        if current.get("rows"):
            selected, coverage = source, current
            break
        if selected is None:
            selected, coverage = source, current
    selected = selected or normalized["provider"]["source"]
    certification = source_certification(
        selected,
        asset_class=normalized["asset"]["assetClass"],
        market=normalized["asset"]["market"],
        venue=normalized["asset"]["venue"],
    )
    fingerprint_input = {
        "scopeHash": scope_hash(normalized),
        "source": selected,
        "coverage": coverage,
        "datasetVersion": certification.get("datasetVersion") if certification else None,
    }
    data_fingerprint = hashlib.sha256(
        json.dumps(fingerprint_input, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return {
        "scope": normalized,
        "scopeHash": fingerprint_input["scopeHash"],
        "dataFingerprint": data_fingerprint,
        "source": selected,
        "sourceAttempts": attempts,
        "certification": certification,
        "coverage": coverage,
        "ready": int(coverage.get("rows") or 0) > 0,
    }


def query(
    scope: DataScope | dict[str, Any],
    *,
    dataset: str = "bars",
    fields: list[str] | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    if dataset == "pit-universe":
        from .pit_data import index_members_as_of_payload

        normalized = normalize_scope(scope)
        universe = (normalized["selection"]["values"] or ["CSI300"])[0]
        as_of = normalized["time"].get("asOfDate") or normalized["time"].get("endDate")
        if not as_of:
            raise ValueError("asOfDate is required for pit-universe")
        payload = index_members_as_of_payload(universe, as_of)
        fingerprint = hashlib.sha256(
            json.dumps(
                {"scopeHash": scope_hash(normalized), "dataset": dataset, "items": payload.get("items")},
                sort_keys=True,
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        return {
            "scope": normalized,
            "scopeHash": scope_hash(normalized),
            "dataFingerprint": fingerprint,
            "dataset": dataset,
            **payload,
        }
    if dataset == "factor-values":
        normalized = normalize_scope(scope)
        names = [str(value) for value in (fields or []) if str(value).strip()]
        clauses = ["trade_date between ? and ?"]
        params: list[Any] = [
            normalized["time"].get("startDate") or "0001-01-01",
            normalized["time"].get("endDate") or "9999-12-31",
        ]
        if normalized["selection"]["values"] and normalized["selection"]["type"] == "symbols":
            clauses.append(f"symbol in ({','.join('?' for _ in normalized['selection']['values'])})")
            params.extend(normalized["selection"]["values"])
        if names:
            clauses.append(f"factor_name in ({','.join('?' for _ in names)})")
            params.extend(names)
        params.append(min(max(int(limit), 1), 1000))
        with db() as connection:
            rows = rows_to_dicts(
                connection.execute(
                    f"""
                    select symbol, trade_date, factor_name, value, source
                    from all_factor_values where {' and '.join(clauses)}
                    order by trade_date, symbol, factor_name limit ?
                    """,
                    params,
                ).fetchall()
            )
        fingerprint = hashlib.sha256(
            json.dumps({"scopeHash": scope_hash(normalized), "dataset": dataset, "items": rows}, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        return {
            "scope": normalized,
            "scopeHash": scope_hash(normalized),
            "dataFingerprint": fingerprint,
            "dataset": dataset,
            "count": len(rows),
            "items": rows,
        }
    if dataset != "bars":
        raise ValueError(f"unsupported_dataset:{dataset}")
    resolution = resolve(scope)
    normalized = resolution["scope"]
    asset = normalized["asset"]
    selection = normalized["selection"]
    time = normalized["time"]
    selected_fields = [field for field in (fields or []) if field in BAR_FIELDS]
    projection = ", ".join(selected_fields) if selected_fields else (
        "symbol, trade_date, open, high, low, close, settle, volume, amount, "
        "turnover_rate, open_interest, prev_close, pct_change, source"
    )
    clauses = [
        "asset_class = ?",
        "market = ?",
        "coalesce(venue, market) = ?",
        "resolution = ?",
        "data_type = ?",
        "adjust = ?",
        "source = ?",
    ]
    params: list[Any] = [
        asset["assetClass"],
        asset["market"],
        asset["venue"],
        asset["resolution"],
        asset["dataType"],
        normalized["price"]["adjust"],
        resolution["source"],
    ]
    if selection["type"] in {"symbols", "products"} and selection["values"]:
        clauses.append(f"symbol in ({','.join('?' for _ in selection['values'])})")
        params.extend(selection["values"])
    if time.get("startDate"):
        clauses.append("trade_date >= ?")
        params.append(time["startDate"])
    if time.get("endDate"):
        clauses.append("trade_date <= ?")
        params.append(time["endDate"])
    params.append(min(max(int(limit), 1), 1000))
    with db() as connection:
        rows = connection.execute(
            f"""
            select {projection} from market_daily_bars
            where {' and '.join(clauses)}
            order by trade_date, symbol limit ?
            """,
            params,
        ).fetchall()
    items = rows_to_dicts(rows)
    return {**resolution, "dataset": dataset, "count": len(items), "items": items}
