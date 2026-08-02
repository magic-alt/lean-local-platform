from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now
from ..domain.data_scope import DataScope
from . import ashare_swing_screen, daily_gap_analysis, data_gateway, ml_research, research_analysis


def preview(template_key: str, scope: DataScope | dict[str, Any], parameters: dict[str, Any]) -> dict[str, Any]:
    research_analysis.template(template_key)
    if template_key == ml_research.TEMPLATE_KEY:
        normalized = data_gateway.normalize_scope(scope)
        return ml_research.preview(parameters, scope=normalized)
    if template_key == ashare_swing_screen.TEMPLATE_KEY:
        normalized = data_gateway.normalize_scope(scope)
        resolved = data_gateway.resolve(normalized)
        payload = ashare_swing_screen.preview(normalized, parameters)
        return {
            **resolved,
            **payload,
            "scope": normalized,
            "scopeHash": resolved["scopeHash"],
            "dataFingerprint": resolved["dataFingerprint"],
        }
    if template_key == daily_gap_analysis.TEMPLATE_KEY:
        normalized = data_gateway.normalize_scope(scope)
        resolved = data_gateway.resolve(normalized)
        return {
            **resolved,
            **daily_gap_analysis.preview(normalized, parameters, resolved=resolved),
            "scope": normalized,
            "scopeHash": resolved["scopeHash"],
            "dataFingerprint": resolved["dataFingerprint"],
        }
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
    if item.get("template_key") == ml_research.TEMPLATE_KEY:
        item["mlResearch"] = ml_research.training_for_research(run_id)
        if item["mlResearch"]:
            item["mlResearch"] = ml_research.training_detail(str(item["mlResearch"]["id"]))
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
    if template_key == ml_research.TEMPLATE_KEY:
        ml_research.validate_scope(normalized, parameters)
    run_id = str(uuid.uuid4())
    item_id = str(uuid.uuid4())
    now = utc_now()
    run_name = str(name or template["name"]).strip() or template["name"]
    queued = template_key == ml_research.TEMPLATE_KEY or research_analysis.is_async_template(template_key)
    with db() as connection:
        connection.execute(
            """
            insert into research_runs
                (id, template_key, name, status, scope_json, parameters_json,
                 cancel_requested, created_at, started_at)
            values (?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (run_id, template_key, run_name, "queued" if queued else "running", json_dump(normalized), json_dump(parameters), now, None if queued else now),
        )
        connection.execute(
            """
            insert into research_run_items
                (id, run_id, item_index, item_key, status, parameters_json, created_at, started_at)
            values (?, ?, 0, ?, ?, ?, ?, ?)
            """,
            (item_id, run_id, template_key, "queued" if queued else "running", json_dump(parameters), now, None if queued else now),
        )
    if template_key == ml_research.TEMPLATE_KEY:
        ml_research.create_training_record(run_id, parameters)
        return get_run(run_id)
    if queued:
        return get_run(run_id)
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


def execute_analysis_run(
    run_id: str,
    *,
    progress=None,
) -> dict[str, Any]:
    item = get_run(run_id)
    if item["status"] in {"success", "failed", "cancelled"}:
        return item
    if not research_analysis.is_async_template(str(item["template_key"])):
        raise ValueError("Research run is not an asynchronous analysis template.")

    def cancelled() -> bool:
        with db() as connection:
            row = connection.execute(
                "select cancel_requested,status from research_runs where id=?",
                (run_id,),
            ).fetchone()
        return bool(row and (row["cancel_requested"] or row["status"] == "cancelled"))

    started = utc_now()
    with db() as connection:
        connection.execute(
            "update research_runs set status='running',started_at=coalesce(started_at,?),error=null where id=?",
            (started, run_id),
        )
        connection.execute(
            "update research_run_items set status='running',started_at=coalesce(started_at,?),error=null where run_id=?",
            (started, run_id),
        )
    try:
        result = research_analysis.analyze(
            str(item["template_key"]),
            item["scope"],
            item["parameters"],
            run_id=run_id,
            cancelled=cancelled,
            progress=progress,
        )
        if cancelled():
            raise RuntimeError("research_run_cancelled")
        finished = utc_now()
        summary = result.get("summary") or {}
        with db() as connection:
            connection.execute(
                """
                update research_runs
                set status='success',result_json=?,summary_json=?,data_fingerprint=?,finished_at=?
                where id=?
                """,
                (json_dump(result), json_dump(summary), result["dataFingerprint"], finished, run_id),
            )
            connection.execute(
                "update research_run_items set status='success',result_json=?,finished_at=? where run_id=?",
                (json_dump(result), finished, run_id),
            )
    except Exception as exc:
        finished = utc_now()
        cancelled_run = str(exc) == "research_run_cancelled" or cancelled()
        status = "cancelled" if cancelled_run else "failed"
        with db() as connection:
            connection.execute(
                "update research_runs set status=?,error=?,finished_at=? where id=?",
                (status, None if cancelled_run else str(exc), finished, run_id),
            )
            connection.execute(
                "update research_run_items set status=?,error=?,finished_at=? where run_id=?",
                (status, None if cancelled_run else str(exc), finished, run_id),
            )
        if not cancelled_run:
            raise
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
    item = get_run(run_id)
    if item.get("template_key") == ashare_swing_screen.TEMPLATE_KEY:
        ashare_swing_screen.remove_artifacts(run_id)
    with db() as connection:
        connection.execute("delete from research_run_items where run_id=?", (run_id,))
        connection.execute("delete from research_runs where id=?", (run_id,))


def artifact_path(run_id: str, artifact_key: str) -> Path:
    item = get_run(run_id)
    if item.get("template_key") == ml_research.TEMPLATE_KEY:
        return ml_research.artifact_path(run_id, artifact_key)
    result = item.get("result") or {}
    artifact = next(
        (entry for entry in result.get("artifacts") or [] if str(entry.get("key")) == artifact_key),
        None,
    )
    if not artifact:
        raise KeyError("Research artifact not found.")
    return ashare_swing_screen.artifact_path(run_id, str(artifact.get("name") or ""))


def backtest_draft(run_id: str) -> dict[str, Any]:
    item = get_run(run_id)
    if item["template_key"] == ml_research.TEMPLATE_KEY:
        raise ValueError("ML_SIGNAL_EXPORT_NOT_IMPLEMENTED")
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
