import uuid
from typing import Any

from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now
from ..domain.assets import asset_request
from ..lean import LeanPlatformError, market_key, normalize_symbol, parse_date
from .ashare_repository import is_tradeable
from .ashare_multisource import quality_gate


def _side(value: str) -> str:
    side = value.strip().lower()
    if side not in {"buy", "sell", "hold"}:
        raise ValueError("Signal side must be buy, sell, or hold.")
    return side


def list_sessions() -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute("select * from paper_sessions order by created_at desc").fetchall()
    return rows_to_dicts(rows)


def get_session(session_id: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute("select * from paper_sessions where id = ?", (session_id,)).fetchone()
    return row_to_dict(row)


def list_signals(session_id: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            "select * from paper_signals where session_id = ? order by trade_date asc, created_at asc",
            (session_id,),
        ).fetchall()
    return rows_to_dicts(rows)


def list_orders(session_id: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            "select * from paper_orders where session_id = ? order by trade_date asc, created_at asc",
            (session_id,),
        ).fetchall()
    return rows_to_dicts(rows)


def list_positions(session_id: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute("select * from paper_positions where session_id = ? order by symbol", (session_id,)).fetchall()
    return rows_to_dicts(rows)


def list_snapshots(session_id: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            "select * from paper_portfolio_snapshots where session_id = ? order by trade_date asc",
            (session_id,),
        ).fetchall()
    return rows_to_dicts(rows)


def create_session(parameters: dict[str, Any]) -> dict[str, Any]:
    request = asset_request(
        parameters["symbol"],
        parameters.get("assetClass", "equity"),
        venue=parameters.get("venue"),
        market=parameters.get("market"),
        resolution=parameters.get("resolution", "daily"),
        data_type=parameters.get("dataType", "trade"),
    )
    cash = float(parameters.get("cash", 100000))
    session_id = str(uuid.uuid4())
    now = utc_now()
    name = parameters.get("name") or f"{request.symbol} Paper Replay"
    clean = {
        **parameters,
        "symbol": request.symbol,
        "assetClass": request.asset_class,
        "venue": request.venue,
        "resolution": request.resolution,
        "dataType": request.data_type,
        "cash": cash,
    }
    with db() as connection:
        connection.execute(
            """
            insert into paper_sessions
                (id, project_id, name, status, symbol, asset_class, venue, resolution, cash, equity, parameters_json, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                parameters.get("projectId"),
                name,
                "created",
                request.symbol,
                request.asset_class,
                request.venue,
                request.resolution,
                cash,
                cash,
                json_dump(clean),
                now,
                now,
            ),
        )
    return get_session(session_id) or {}


def update_session_status(session_id: str, status: str) -> dict[str, Any]:
    if status not in {"created", "running", "paused", "stopped"}:
        raise ValueError("Paper session status must be created, running, paused, or stopped.")
    now = utc_now()
    finished_at = now if status == "stopped" else None
    with db() as connection:
        connection.execute(
            "update paper_sessions set status = ?, updated_at = ?, finished_at = coalesce(?, finished_at) where id = ?",
            (status, now, finished_at, session_id),
        )
    return get_session(session_id) or {}


def _ashare_bar(symbol: str, trade_date: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute(
            """
            select * from ashare_daily_bars
            where symbol = ? and trade_date = ? and adjust = 'raw'
            order by source desc
            limit 1
            """,
            (symbol, trade_date),
        ).fetchone()
    return row_to_dict(row)


def _latest_ashare_bars(symbol: str, trade_date: str, limit: int) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            """
            select * from ashare_daily_bars
            where symbol = ? and trade_date <= ? and adjust = 'raw'
            order by trade_date desc
            limit ?
            """,
            (symbol, trade_date, limit),
        ).fetchall()
    return list(reversed(rows_to_dicts(rows)))


def create_signal(
    session_id: str,
    *,
    trade_date: str,
    side: str,
    target_percent: float | None = None,
    strength: float | None = None,
    reason: str | None = None,
    source: str = "manual",
) -> dict[str, Any]:
    session = get_session(session_id)
    if not session:
        raise KeyError("Paper session not found.")
    signal_id = str(uuid.uuid4())
    now = utc_now()
    with db() as connection:
        connection.execute(
            """
            insert into paper_signals
                (id, session_id, trade_date, symbol, side, target_percent, strength, reason, status, source, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal_id,
                session_id,
                parse_date(trade_date).isoformat(),
                session["symbol"],
                _side(side),
                target_percent,
                strength,
                reason,
                "created",
                source,
                now,
            ),
        )
    return _get_signal(signal_id) or {}


def _get_signal(signal_id: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute("select * from paper_signals where id = ?", (signal_id,)).fetchone()
    return row_to_dict(row)


def generate_daily_signal(session_id: str, trade_date: str) -> dict[str, Any]:
    session = get_session(session_id)
    if not session:
        raise KeyError("Paper session not found.")
    parameters = session.get("parameters") or {}
    symbol = session["symbol"]
    date_value = parse_date(trade_date).isoformat()
    fast = int(parameters.get("fast") or parameters.get("parameters", {}).get("fast") or 5)
    slow = int(parameters.get("slow") or parameters.get("parameters", {}).get("slow") or 20)
    if fast >= slow:
        slow = fast + 1
    bars = _latest_ashare_bars(symbol, date_value, slow)
    if len(bars) < slow:
        return create_signal(
            session_id,
            trade_date=date_value,
            side="hold",
            target_percent=None,
            strength=0,
            reason=f"insufficient_history:{len(bars)}/{slow}",
            source="ema_cross",
        )
    fast_average = sum(float(row["close"]) for row in bars[-fast:]) / fast
    slow_average = sum(float(row["close"]) for row in bars[-slow:]) / slow
    position = _position(session_id, symbol)
    holding = bool(position and float(position.get("quantity") or 0) > 0)
    if fast_average > slow_average and not holding:
        return create_signal(session_id, trade_date=date_value, side="buy", target_percent=1.0, strength=fast_average - slow_average, reason="fast_ma_above_slow_ma", source="ema_cross")
    if fast_average < slow_average and holding:
        return create_signal(session_id, trade_date=date_value, side="sell", target_percent=0.0, strength=slow_average - fast_average, reason="fast_ma_below_slow_ma", source="ema_cross")
    return create_signal(session_id, trade_date=date_value, side="hold", target_percent=None, strength=abs(fast_average - slow_average), reason="no_rebalance", source="ema_cross")


def _position(session_id: str, symbol: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute(
            "select * from paper_positions where session_id = ? and symbol = ?",
            (session_id, symbol),
        ).fetchone()
    return row_to_dict(row)


def _open_signals(session_id: str, trade_date: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            """
            select * from paper_signals
            where session_id = ? and trade_date = ? and status = 'created'
            order by created_at asc
            """,
            (session_id, trade_date),
        ).fetchall()
    return rows_to_dicts(rows)


def _signals_for_date(session_id: str, trade_date: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            """
            select * from paper_signals
            where session_id = ? and trade_date = ?
            order by created_at asc
            """,
            (session_id, trade_date),
        ).fetchall()
    return rows_to_dicts(rows)


def _fee(quantity: float, price: float, side: str, session: dict[str, Any]) -> float:
    parameters = session.get("parameters") or {}
    value = abs(quantity * price)
    commission = max(value * float(parameters.get("commissionRate") or 0.0003), float(parameters.get("minCommission") or 5.0)) if value else 0
    stamp_tax = value * float(parameters.get("stampTaxSell") or 0.001) if side == "sell" else 0
    transfer = value * float(parameters.get("transferFeeRate") or 0.00001)
    return commission + stamp_tax + transfer


def _round_lot(quantity: float, lot_size: int = 100) -> int:
    if quantity == 0:
        return 0
    sign = 1 if quantity > 0 else -1
    return sign * (abs(int(quantity)) // lot_size) * lot_size


def _update_signal(signal_id: str, status: str) -> None:
    with db() as connection:
        connection.execute("update paper_signals set status = ? where id = ?", (status, signal_id))


def _record_order(
    session_id: str,
    signal: dict[str, Any],
    side: str,
    quantity: float,
    trade_date: str,
    order_price: float | None,
    fill_price: float | None,
    fee: float,
    status: str,
    reason: str | None = None,
) -> dict[str, Any]:
    order_id = str(uuid.uuid4())
    now = utc_now()
    with db() as connection:
        connection.execute(
            """
            insert into paper_orders
                (id, session_id, signal_id, trade_date, symbol, side, quantity, order_price,
                 fill_price, fee, status, reason, created_at, filled_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_id,
                session_id,
                signal.get("id"),
                trade_date,
                signal["symbol"],
                side,
                quantity,
                order_price,
                fill_price,
                fee,
                status,
                reason,
                now,
                now if status == "filled" else None,
            ),
        )
    with db() as connection:
        row = connection.execute("select * from paper_orders where id = ?", (order_id,)).fetchone()
    return row_to_dict(row) or {}


def _apply_fill(session: dict[str, Any], symbol: str, side: str, quantity: float, price: float, fee: float, trade_date: str) -> None:
    position = _position(session["id"], symbol)
    current_quantity = float((position or {}).get("quantity") or 0)
    average_price = float((position or {}).get("average_price") or 0)
    cash = float(session["cash"])
    signed = quantity if side == "buy" else -quantity
    new_quantity = current_quantity + signed
    if side == "buy":
        cost = quantity * price + fee
        cash -= cost
        average_price = ((current_quantity * average_price) + (quantity * price)) / new_quantity if new_quantity else 0
        last_buy_date = trade_date
    else:
        cash += quantity * price - fee
        last_buy_date = (position or {}).get("last_buy_date")
        if new_quantity <= 0:
            average_price = 0
    now = utc_now()
    with db() as connection:
        if new_quantity <= 0:
            connection.execute("delete from paper_positions where session_id = ? and symbol = ?", (session["id"], symbol))
        else:
            connection.execute(
                """
                insert into paper_positions
                    (session_id, symbol, quantity, average_price, market_price, market_value, last_buy_date, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(session_id, symbol) do update set
                    quantity = excluded.quantity,
                    average_price = excluded.average_price,
                    market_price = excluded.market_price,
                    market_value = excluded.market_value,
                    last_buy_date = excluded.last_buy_date,
                    updated_at = excluded.updated_at
                """,
                (session["id"], symbol, new_quantity, average_price, price, new_quantity * price, last_buy_date, now),
            )
        connection.execute("update paper_sessions set cash = ?, updated_at = ? where id = ?", (cash, now, session["id"]))


def match_daily_orders(session_id: str, trade_date: str, auto_signal: bool = True) -> dict[str, Any]:
    session = get_session(session_id)
    if not session:
        raise KeyError("Paper session not found.")
    date_value = parse_date(trade_date).isoformat()
    if auto_signal and not _signals_for_date(session_id, date_value):
        generate_daily_signal(session_id, date_value)
    signals = _open_signals(session_id, date_value)
    orders = []
    for signal in signals:
        side = signal["side"]
        if side == "hold":
            _update_signal(signal["id"], "processed")
            continue
        gate = quality_gate(signal["symbol"], date_value)
        if not gate["passed"]:
            report_id = gate["blockingReports"][0].get("id") if gate["blockingReports"] else None
            reason = f"qa_failed:{report_id}" if report_id else "qa_failed"
            orders.append(_record_order(session_id, signal, side, 0, date_value, None, None, 0, "rejected", reason))
            _update_signal(signal["id"], "rejected")
            continue
        bar = _ashare_bar(signal["symbol"], date_value)
        if not bar:
            orders.append(_record_order(session_id, signal, side, 0, date_value, None, None, 0, "rejected", "bar_missing"))
            _update_signal(signal["id"], "rejected")
            continue
        can_trade, reason = is_tradeable(signal["symbol"], date_value, side)
        if not can_trade:
            orders.append(_record_order(session_id, signal, side, 0, date_value, float(bar["close"]), None, 0, "rejected", reason))
            _update_signal(signal["id"], "rejected")
            continue
        session = get_session(session_id) or session
        position = _position(session_id, signal["symbol"])
        current_quantity = float((position or {}).get("quantity") or 0)
        price = float(bar["close"])
        lot_size = int((session.get("parameters") or {}).get("lotSize") or 100)
        if side == "buy":
            target = float(signal.get("target_percent") or 1.0)
            desired = _round_lot((float(session["equity"]) * target) / price, lot_size)
            quantity = max(0, desired - current_quantity)
            quantity = _round_lot(quantity, lot_size)
            fee = _fee(quantity, price, side, session)
            max_cash_quantity = _round_lot((float(session["cash"]) - fee) / price, lot_size)
            quantity = max(0, min(quantity, max_cash_quantity))
            if quantity <= 0:
                orders.append(_record_order(session_id, signal, side, 0, date_value, price, None, 0, "rejected", "insufficient_cash"))
                _update_signal(signal["id"], "rejected")
                continue
        else:
            if (position or {}).get("last_buy_date") == date_value:
                orders.append(_record_order(session_id, signal, side, 0, date_value, price, None, 0, "rejected", "t_plus_1"))
                _update_signal(signal["id"], "rejected")
                continue
            quantity = _round_lot(current_quantity, lot_size)
            fee = _fee(quantity, price, side, session)
        if quantity <= 0:
            reason = "insufficient_position" if side == "sell" else "lot_size"
            orders.append(_record_order(session_id, signal, side, 0, date_value, price, None, 0, "rejected", reason))
            _update_signal(signal["id"], "rejected")
            continue
        fee = _fee(quantity, price, side, session)
        _apply_fill(session, signal["symbol"], side, quantity, price, fee, date_value)
        orders.append(_record_order(session_id, signal, side, quantity, date_value, price, price, fee, "filled"))
        _update_signal(signal["id"], "filled")
    snapshot = create_snapshot(session_id, date_value)
    return {"date": date_value, "signals": signals, "orders": orders, "snapshot": snapshot}


def _replay_dates(session: dict[str, Any], start_date: str, end_date: str) -> list[str]:
    start = parse_date(start_date).isoformat()
    end = parse_date(end_date).isoformat()
    symbol = session["symbol"]
    if session.get("asset_class") == "equity" and session.get("venue") == "china":
        with db() as connection:
            calendar_rows = connection.execute(
                """
                select trade_date
                from trade_calendar
                where market = 'china' and is_open = 1 and trade_date between ? and ?
                order by trade_date asc
                """,
                (start, end),
            ).fetchall()
        dates = [row["trade_date"] for row in calendar_rows]
        if dates:
            return dates
        with db() as connection:
            rows = connection.execute(
                """
                select distinct trade_date
                from ashare_daily_bars
                where symbol = ? and trade_date between ? and ?
                order by trade_date asc
                """,
                (symbol, start, end),
            ).fetchall()
        return [row["trade_date"] for row in rows]
    return []


def run_replay(session_id: str, start_date: str, end_date: str, auto_signal: bool = True) -> dict[str, Any]:
    session = get_session(session_id)
    if not session:
        raise KeyError("Paper session not found.")
    dates = _replay_dates(session, start_date, end_date)
    update_session_status(session_id, "running")
    days = []
    try:
        for trade_date in dates:
            days.append(match_daily_orders(session_id, trade_date, auto_signal=auto_signal))
    finally:
        update_session_status(session_id, "paused")
    return {
        "sessionId": session_id,
        "startDate": parse_date(start_date).isoformat(),
        "endDate": parse_date(end_date).isoformat(),
        "tradingDays": len(dates),
        "days": days,
        "finalSession": get_session(session_id),
        "positions": list_positions(session_id),
        "snapshots": list_snapshots(session_id),
    }


def create_snapshot(session_id: str, trade_date: str) -> dict[str, Any]:
    session = get_session(session_id)
    if not session:
        raise KeyError("Paper session not found.")
    date_value = parse_date(trade_date).isoformat()
    positions = list_positions(session_id)
    market_value = 0.0
    for position in positions:
        bar = _ashare_bar(position["symbol"], date_value)
        price = float((bar or {}).get("close") or position.get("market_price") or position.get("average_price") or 0)
        value = float(position["quantity"]) * price
        market_value += value
        with db() as connection:
            connection.execute(
                "update paper_positions set market_price = ?, market_value = ?, updated_at = ? where session_id = ? and symbol = ?",
                (price, value, utc_now(), session_id, position["symbol"]),
            )
    cash = float(session["cash"])
    equity = cash + market_value
    snapshot_id = str(uuid.uuid4())
    now = utc_now()
    with db() as connection:
        connection.execute(
            """
            insert into paper_portfolio_snapshots
                (id, session_id, trade_date, cash, market_value, equity, positions_json, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(session_id, trade_date) do update set
                cash = excluded.cash,
                market_value = excluded.market_value,
                equity = excluded.equity,
                positions_json = excluded.positions_json,
                created_at = excluded.created_at
            """,
            (snapshot_id, session_id, date_value, cash, market_value, equity, json_dump(list_positions(session_id)), now),
        )
        connection.execute("update paper_sessions set equity = ?, updated_at = ? where id = ?", (equity, now, session_id))
        row = connection.execute(
            "select * from paper_portfolio_snapshots where session_id = ? and trade_date = ?",
            (session_id, date_value),
        ).fetchone()
    return row_to_dict(row) or {}
