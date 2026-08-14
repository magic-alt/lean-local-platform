from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import polars as pl

from ..db import db


def _qlib_instrument(symbol: str, exchange: str) -> str:
    code = (
        str(symbol)
        .strip()
        .upper()
        .replace(".SH", "")
        .replace(".SZ", "")
        .replace(".BJ", "")
    )
    venue = str(exchange).strip().upper()
    prefixes = {"SSE": "SH", "SHSE": "SH", "SZSE": "SZ", "BSE": "BJ"}
    prefix = prefixes.get(venue)
    if prefix is None or len(code) != 6 or not code.isdigit():
        raise ValueError(f"Unknown A-share exchange or symbol: {symbol}/{exchange}")
    return f"{prefix}{code}"


def export_industry_classification_pit(
    output_path: str | Path,
    *,
    start: str,
    end: str,
    taxonomy: str = "SW2021",
    level_no: int = 1,
) -> dict[str, Any]:
    if taxonomy != "SW2021" or level_no != 1:
        raise ValueError("industry_classification_pit requires SW2021 level 1")
    if not start or not end or end < start:
        raise ValueError("industry classification coverage must be ordered")
    with db() as connection:
        rows = connection.execute(
            """select i.symbol,i.industry_code,i.industry_name,i.taxonomy,i.level_no,
                      i.in_date,i.out_date,i.source,i.payload_hash,s.exchange
               from industry_membership i
               join securities s on s.symbol=i.symbol
               where i.taxonomy=? and i.level_no=? and i.in_date<=?
                 and coalesce(i.out_date,?)>=?
               order by i.symbol,i.in_date,i.industry_code""",
            (taxonomy, level_no, end, end, start),
        ).fetchall()
    normalized: list[dict[str, Any]] = []
    previous: dict[str, tuple[str, str]] = {}
    for row in rows:
        instrument = _qlib_instrument(str(row["symbol"]), str(row["exchange"]))
        effective_from = max(start, str(row["in_date"])[:10])
        effective_to = min(end, str(row["out_date"] or end)[:10])
        prior = previous.get(instrument)
        if prior is not None and effective_from <= prior[1]:
            raise ValueError(f"Overlapping PIT industry intervals: {instrument}")
        previous[instrument] = (effective_from, effective_to)
        normalized.append(
            {
                "instrument": instrument,
                "effective_from": effective_from,
                "effective_to": effective_to,
                "industry_code": str(row["industry_code"]),
                "industry_name": row["industry_name"],
                "taxonomy": taxonomy,
                "level_no": level_no,
                "source": str(row["source"]),
                "payload_hash": str(row["payload_hash"]),
            }
        )
    if not normalized:
        raise ValueError("industry_classification_pit contains no rows")
    target = Path(output_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    pl.DataFrame(normalized).write_parquet(temporary, compression="zstd")
    os.replace(temporary, target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    identity = {
        "taxonomy": taxonomy,
        "levelNo": level_no,
        "coverage": {"start": start, "end": end},
        "sha256": digest,
    }
    return {
        "role": "industry_classification_pit",
        "componentReleaseId": "component:industry_classification_pit:"
        + hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "datasetKey": "industry_classification_pit",
        "schemaVersion": "1",
        "coverage": identity["coverage"],
        "files": [{"path": str(target), "sha256": digest, "rowCount": len(normalized)}],
    }
