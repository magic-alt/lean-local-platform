from __future__ import annotations

import os
from datetime import date
from typing import Any

from ..core.errors import LeanWebError


def jqdata_symbol(symbol: str) -> str:
    value = str(symbol or "").strip().upper()
    if "." in value:
        return value
    raw = value[-6:] if len(value) >= 6 else value
    if raw.startswith(("5", "6", "9")) or raw in {"000300", "000905", "000852"}:
        return f"{raw}.XSHG"
    if raw.startswith(("0", "1", "2", "3")):
        return f"{raw}.XSHE"
    if raw.startswith(("4", "8")):
        return f"{raw}.XBEI"
    return raw


def _adjust_flag(adjust: str | None) -> str | None:
    value = str(adjust or "raw").strip().lower()
    if value in {"qfq", "pre", "forward"}:
        return "pre"
    if value in {"hfq", "post", "backward"}:
        return "post"
    return None


def _auth() -> Any:
    try:
        import jqdatasdk as jq  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency.
        raise LeanWebError("jqdatasdk is not installed. Install it before using provider=jqdata.") from exc

    token = os.environ.get("JQDATA_TOKEN")
    username = os.environ.get("JQDATA_USERNAME")
    password = os.environ.get("JQDATA_PASSWORD")
    if token:
        jq.auth_by_token(token)
    elif username and password:
        jq.auth(username, password)
    else:
        raise LeanWebError("JQData credentials missing. Set JQDATA_TOKEN or JQDATA_USERNAME/JQDATA_PASSWORD in .env.")
    if hasattr(jq, "is_auth") and not jq.is_auth():
        raise LeanWebError("JQData authentication failed.")
    return jq


def fetch_jqdata_rows(
    symbol: str,
    start: str | None = None,
    end: str | None = None,
    adjust: str | None = None,
) -> list[dict[str, Any]]:
    jq = _auth()
    security = jqdata_symbol(symbol)
    frame = jq.get_price(
        security,
        start_date=start or "1990-01-01",
        end_date=end or date.today().isoformat(),
        frequency="daily",
        fields=["open", "close", "high", "low", "volume", "money", "pre_close"],
        skip_paused=False,
        fq=_adjust_flag(adjust),
        panel=False,
    )
    if frame is None or getattr(frame, "empty", False):
        raise LeanWebError(f"JQData returned no daily rows for {symbol}.")
    rows: list[dict[str, Any]] = []
    records = frame.reset_index().to_dict("records") if hasattr(frame, "reset_index") else []
    for row in records:
        time_value = row.get("time") or row.get("date") or row.get("index") or row.get("level_0")
        if not time_value:
            continue
        rows.append(
            {
                "date": str(time_value)[:10],
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": row.get("close"),
                "volume": row.get("volume"),
                "amount": row.get("money") or row.get("amount"),
                "prev_close": row.get("pre_close"),
            }
        )
    if not rows:
        raise LeanWebError(f"JQData returned no parseable daily rows for {symbol}.")
    return rows
