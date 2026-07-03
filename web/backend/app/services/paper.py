import uuid
from typing import Any

from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now
from ..domain.assets import asset_request


def list_sessions() -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute("select * from paper_sessions order by created_at desc").fetchall()
    return rows_to_dicts(rows)


def get_session(session_id: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute("select * from paper_sessions where id = ?", (session_id,)).fetchone()
    return row_to_dict(row)


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

