from __future__ import annotations

from datetime import timedelta

from ..db import db
from ..lean_engine.symbols import parse_date


def next_trade_date(market: str, value: str) -> str:
    """Return the next governed open date, with a weekday-only fallback."""
    current = parse_date(value)
    market_value = str(market or "china").lower()
    with db() as connection:
        row = connection.execute(
            """
            select trade_date from trade_calendar
            where market = ? and is_open = 1 and trade_date > ?
            order by trade_date asc limit 1
            """,
            (market_value, current.isoformat()),
        ).fetchone()
    if row:
        return str(row["trade_date"])
    candidate = current + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate.isoformat()
