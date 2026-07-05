from __future__ import annotations

import csv
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.errors import LeanWebError


def contract_code_from_tq_symbol(symbol: str) -> str:
    value = symbol.strip()
    if "@" in value:
        return value.split("@", 1)[1].split(".")[-1].upper()
    return value.split(".")[-1].upper()


def exchange_from_tq_symbol(symbol: str) -> str:
    value = symbol.strip()
    tail = value.split("@", 1)[1] if "@" in value else value
    if "." in tail:
        return tail.split(".", 1)[0].upper()
    return ""


def normalize_tqsdk_kline_rows(symbol: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    contract_code = contract_code_from_tq_symbol(symbol)
    normalized: list[dict[str, Any]] = []
    for row in rows:
        time_value = row.get("datetime") or row.get("time") or row.get("date")
        if not time_value:
            continue
        normalized.append(
            {
                "contract_code": str(row.get("contract_code") or row.get("symbol") or contract_code).split(".")[-1].upper(),
                "timestamp": str(time_value).replace("T", " ").replace("Z", "")[:19],
                "trade_date": str(time_value)[:10],
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": row.get("close"),
                "volume": row.get("volume"),
                "open_interest": row.get("open_interest") or row.get("openInterest") or row.get("close_oi") or row.get("close_oi".upper()),
            }
        )
    normalized.sort(key=lambda item: item["timestamp"])
    return normalized


def _read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def download_tqsdk_klines(
    *,
    symbol: str,
    start_date: str,
    end_date: str,
    duration_seconds: int = 86400,
    tq_account: str | None = None,
    tq_password: str | None = None,
) -> list[dict[str, Any]]:
    try:
        from tqsdk import TqApi, TqAuth  # type: ignore
        from tqsdk.tools import DataDownloader  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency.
        raise LeanWebError("tqsdk is not installed. Install it before using provider=tqsdk.") from exc

    auth = TqAuth(tq_account, tq_password) if tq_account and tq_password else None
    api = TqApi(auth=auth) if auth else TqApi()
    with tempfile.NamedTemporaryFile(prefix="tqsdk-", suffix=".csv", delete=False) as handle:
        csv_path = Path(handle.name)
    try:
        downloader = DataDownloader(
            api,
            symbol_list=symbol,
            dur_sec=int(duration_seconds),
            start_dt=datetime.fromisoformat(start_date),
            end_dt=datetime.fromisoformat(end_date),
            csv_file_name=str(csv_path),
        )
        while not downloader.is_finished():
            api.wait_update()
        return normalize_tqsdk_kline_rows(symbol, _read_csv(csv_path))
    finally:
        try:
            api.close()
        finally:
            try:
                csv_path.unlink()
            except FileNotFoundError:
                pass
