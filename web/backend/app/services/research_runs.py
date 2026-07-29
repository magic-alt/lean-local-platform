from __future__ import annotations

import uuid
from typing import Any

from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now
from ..domain.data_scope import DataScope
from . import data_gateway, research_analysis


def preview(template_key: str, scope: DataScope | dict[str, Any], parameters: dict[str, Any]) -> dict[str, Any]:
    research_analysis.template(template_key)
    resolved = data_gateway.resolve(scope)
    return {
        **resolved,
        "template": template_key,
        "parameters": parameters,
        "blocking": [] if resolved["ready"] or template_key in {"universe-pit", "cbond-double-low", "factor-evaluation", "futures-continuous"} else ["data_unavailable"],
    }


def list_runs(limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            "select * from research_runs order by created_at desc limit ? offset ?",
            (min(max(limit, 1), 500), max(offset, 0)),
        ).fetchall()
    return rows_to_dicts(rows)


def get_run(run_id: str) -> dict[str, Any]:
    with db() as connection:
        row = connection.execute("select * from research_runs where id=?", (run_id,)).fetchone()
    item = row_to_dict(row)
    if item is None:
        raise KeyError("Research run not found.")
    return item


def create_run(
    *,
    template_key: str,
    name: str | None,
    scope: DataScope | dict[str, Any],
    parameters: dict[str, Any],
) -> dict[str, Any]:
    template = research_analysis.template(template_key)
    normalized = data_gateway.normalize_scope(scope)
    run_id = str(uuid.uuid4())
    item_id = str(uuid.uuid4())
    now = utc_now()
    run_name = str(name or template["name"]).strip() or template["name"]
    with db() as connection:
        connection.execute(
            """
            insert into research_runs
                (id, template_key, name, status, scope_json, parameters_json,
                 cancel_requested, created_at, started_at)
            values (?, ?, ?, 'running', ?, ?, 0, ?, ?)
            """,
            (run_id, template_key, run_name, json_dump(normalized), json_dump(parameters), now, now),
        )
        connection.execute(
            """
            insert into research_run_items
                (id, run_id, item_index, item_key, status, parameters_json, created_at, started_at)
            values (?, ?, 0, ?, 'running', ?, ?, ?)
            """,
            (item_id, run_id, template_key, json_dump(parameters), now, now),
        )
    try:
        result = research_analysis.analyze(template_key, normalized, parameters)
        finished = utc_now()
        summary = result.get("summary") or {}
        with db() as connection:
            connection.execute(
                """
                update research_runs
                set status='success', result_json=?, summary_json=?, data_fingerprint=?, finished_at=?
                where id=?
                """,
                (json_dump(result), json_dump(summary), result["dataFingerprint"], finished, run_id),
            )
            connection.execute(
                "update research_run_items set status='success', result_json=?, finished_at=? where id=?",
                (json_dump(result), finished, item_id),
            )
    except Exception as exc:
        finished = utc_now()
        with db() as connection:
            connection.execute(
                "update research_runs set status='failed', error=?, finished_at=? where id=?",
                (str(exc), finished, run_id),
            )
            connection.execute(
                "update research_run_items set status='failed', error=?, finished_at=? where id=?",
                (str(exc), finished, item_id),
            )
    return get_run(run_id)


def cancel_run(run_id: str) -> dict[str, Any]:
    item = get_run(run_id)
    if item["status"] in {"success", "failed", "cancelled"}:
        return item
    with db() as connection:
        connection.execute(
            "update research_runs set status='cancelled', cancel_requested=1, finished_at=? where id=?",
            (utc_now(), run_id),
        )
        connection.execute(
            "update research_run_items set status='cancelled', finished_at=? where run_id=? and status in ('queued','running')",
            (utc_now(), run_id),
        )
    return get_run(run_id)


def retry_run(run_id: str) -> dict[str, Any]:
    item = get_run(run_id)
    return create_run(
        template_key=str(item["template_key"]),
        name=f"{item['name']} · retry",
        scope=item["scope"],
        parameters=item["parameters"],
    )


def delete_run(run_id: str) -> None:
    get_run(run_id)
    with db() as connection:
        connection.execute("delete from research_run_items where run_id=?", (run_id,))
        connection.execute("delete from research_runs where id=?", (run_id,))


def backtest_draft(run_id: str) -> dict[str, Any]:
    item = get_run(run_id)
    if item["status"] != "success":
        raise ValueError("Only a successful research run can create a backtest draft.")
    resolved = data_gateway.resolve(item["scope"])
    values = list((item["scope"].get("selection") or {}).get("values") or [])
    selection_type = str((item["scope"].get("selection") or {}).get("type") or "symbols")
    target = "backtest" if selection_type in {"symbols", "products"} and len(values) == 1 else "batch"
    return {
        "sourceResearchRunId": run_id,
        "dataScope": item["scope"],
        "scopeHash": resolved["scopeHash"],
        "dataFingerprint": item.get("data_fingerprint") or resolved["dataFingerprint"],
        "target": target,
        "strategyRequired": True,
        "preflightRequired": True,
        "note": "Research data scope is preserved; order, fee, slippage and portfolio assumptions must be configured in Backtest.",
    }
