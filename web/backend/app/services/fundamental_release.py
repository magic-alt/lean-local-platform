from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

import polars as pl


PIT_FUNDAMENTAL_V2_FIELDS = (
    "roe_waa_pit",
    "roa_pit",
    "netprofit_margin_pit",
    "netprofit_yoy_pit",
    "or_yoy_pit",
    "debt_to_assets_pit",
    "ocf_to_or_pit",
    "total_assets_pit",
    "prior_year_total_assets_pit",
    "total_equity_pit",
    "prior_year_total_equity_pit",
    "gross_profit_ttm_pit",
    "prior_year_gross_profit_ttm_pit",
    "operating_profit_ttm_pit",
    "prior_year_operating_profit_ttm_pit",
    "operating_cash_flow_ttm_pit",
    "prior_year_operating_cash_flow_ttm_pit",
    "revenue_ttm_pit",
    "prior_year_revenue_ttm_pit",
    "parent_net_income_ttm_pit",
    "prior_year_parent_net_income_ttm_pit",
    "capex_ttm_pit",
    "fixed_assets_pit",
    "total_shares_pit",
)


def _date(value: object, name: str) -> str:
    text = str(value or "")[:10]
    try:
        return str(pl.Series([text]).str.to_date(strict=True)[0])
    except Exception as exc:
        raise ValueError(f"invalid {name}: {value}") from exc


def _number(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
        return number if number == number and abs(number) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _canonical_report(row: Mapping[str, Any]) -> dict[str, Any]:
    symbol = str(row.get("instrument") or row.get("symbol") or "").strip().upper()
    if not symbol:
        raise ValueError("PIT fundamental report requires instrument")
    announcement = _date(row.get("ann_date"), "ann_date")
    final_announcement = row.get("f_ann_date")
    source_announcement = max(
        announcement,
        _date(final_announcement, "f_ann_date") if final_announcement else announcement,
    )
    result: dict[str, Any] = {
        "instrument": symbol,
        "source_period": _date(row.get("end_date"), "end_date"),
        "source_ann_date": source_announcement,
        "update_flag": str(row.get("update_flag") or "0"),
        "observed_at": str(row.get("observed_at") or row.get("ingest_time") or ""),
        "payload_hash": str(row.get("payload_hash") or ""),
    }
    result.update({field: _number(row.get(field)) for field in PIT_FUNDAMENTAL_V2_FIELDS})
    return result


def build_pit_fundamentals_v2(
    reports: Sequence[Mapping[str, Any]],
    trading_calendar: Sequence[str],
) -> pl.DataFrame:
    """Expand standardized report facts from the first open day after publication.

    Upstream typed-source normalization owns TTM/prior-comparable construction.
    This release boundary owns revision choice, effective-date causality and the
    immutable daily panel consumed by Qlib.
    """

    open_dates = sorted({_date(value, "trading_calendar") for value in trading_calendar})
    if not open_dates:
        raise ValueError("PIT fundamental release requires a trading calendar")
    normalized = [_canonical_report(row) for row in reports]
    if not normalized:
        raise ValueError("PIT fundamental release contains no reports")
    events: list[dict[str, Any]] = []
    for row in normalized:
        effective = next((date for date in open_dates if date > row["source_ann_date"]), None)
        if effective is not None:
            events.append({**row, "effective_date": effective})
    if not events:
        raise ValueError("no PIT fundamental report becomes effective inside coverage")
    events.sort(
        key=lambda item: (
            item["instrument"],
            item["effective_date"],
            item["source_period"],
            item["update_flag"],
            item["observed_at"],
            item["payload_hash"],
        )
    )
    output: list[dict[str, Any]] = []
    by_instrument: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        by_instrument.setdefault(str(event["instrument"]), []).append(event)
    for instrument, instrument_events in sorted(by_instrument.items()):
        known: dict[str, dict[str, Any]] = {}
        cursor = 0
        for trade_date in open_dates:
            while cursor < len(instrument_events) and instrument_events[cursor]["effective_date"] <= trade_date:
                event = instrument_events[cursor]
                known[str(event["source_period"])] = event
                cursor += 1
            if not known:
                continue
            latest = known[max(known)]
            output.append(
                {
                    "instrument": instrument,
                    "trade_date": trade_date,
                    "source_period": latest["source_period"],
                    "source_ann_date": latest["source_ann_date"],
                    "effective_date": latest["effective_date"],
                    **{field: latest[field] for field in PIT_FUNDAMENTAL_V2_FIELDS},
                }
            )
    return pl.DataFrame(output).sort(["trade_date", "instrument"])


def export_pit_fundamentals_v2(
    reports: Sequence[Mapping[str, Any]],
    trading_calendar: Sequence[str],
    output_path: str | Path,
) -> dict[str, Any]:
    frame = build_pit_fundamentals_v2(reports, trading_calendar)
    target = Path(output_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    frame.write_parquet(temporary, compression="zstd")
    os.replace(temporary, target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    coverage = {
        "start": str(frame.select(pl.col("trade_date").min()).item()),
        "end": str(frame.select(pl.col("trade_date").max()).item()),
    }
    identity = {
        "schemaVersion": "pit-fundamentals-v2",
        "coverage": coverage,
        "fields": list(PIT_FUNDAMENTAL_V2_FIELDS),
        "sha256": digest,
    }
    return {
        "role": "pit_fundamentals",
        "componentReleaseId": "component:pit_fundamentals:"
        + hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "datasetKey": "pit_fundamentals_v2",
        "schemaVersion": "2",
        "coverage": coverage,
        "files": [{"path": str(target), "sha256": digest, "rowCount": frame.height}],
    }
