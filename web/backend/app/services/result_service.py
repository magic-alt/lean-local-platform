from __future__ import annotations

from pathlib import Path
from typing import Any

from ..db import utc_now
from ..parsers.lean_result_parser import parse_result_payload
from ..repositories.backtest_repository import get_result, save_result
from .db_object_store import put_file


def _artifact_content_type(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "application/json"
    if suffix in {".txt", ".log", ".csv"}:
        return "text/plain"
    if suffix == ".html":
        return "text/html"
    if suffix == ".py":
        return "text/x-python"
    return None


def _artifact_kind(path: Path) -> str:
    name = path.name
    if name == "config.json":
        return "lean-config"
    if name == "artifact-manifest.json":
        return "artifact-manifest"
    if name.endswith("-summary.json"):
        return "lean-summary"
    if name.endswith("-order-events.json"):
        return "lean-order-events"
    if name.endswith("-log.txt") or name == "log.txt":
        return "lean-log"
    if name == "stdout.log":
        return "lean-stdout"
    if name.startswith("data-monitor-report-"):
        return "lean-data-monitor-report"
    if name.startswith("succeeded-data-requests-"):
        return "lean-data-requests-succeeded"
    if name.startswith("failed-data-requests-"):
        return "lean-data-requests-failed"
    if name == "report.html":
        return "html-report"
    if name == "ashare_trade_status.json":
        return "ashare-trade-status"
    if name == "ashare_execution.py":
        return "ashare-execution-helper"
    if name.endswith(".json"):
        return "lean-result"
    return "artifact"


def _artifact_paths(job_id: str, result_json: Path, summary_json: Path | None, run: dict[str, Any]) -> list[Path]:
    paths: list[Path] = [result_json]
    if summary_json:
        paths.append(summary_json)
    for key in ("report_html_path",):
        value = run.get(key)
        if value:
            paths.append(Path(value))
    results_dir = Path(run.get("results_dir") or result_json.parent)
    work_dir = Path(run.get("work_dir") or results_dir.parent)
    for candidate in (
        results_dir / f"{job_id}-order-events.json",
        results_dir / f"{job_id}-log.txt",
        results_dir / "log.txt",
        results_dir / "stdout.log",
        results_dir / "report.html",
        results_dir / "artifact-manifest.json",
        work_dir / "config.json",
        work_dir / "ashare_trade_status.json",
        work_dir / "ashare_execution.py",
    ):
        paths.append(candidate)
    if results_dir.exists():
        paths.extend(sorted(results_dir.glob("data-monitor-report-*.json")))
        paths.extend(sorted(results_dir.glob("succeeded-data-requests-*.txt")))
        paths.extend(sorted(results_dir.glob("failed-data-requests-*.txt")))

    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            resolved = str(path.resolve())
        except OSError:
            resolved = str(path)
        if resolved in seen or not path.exists() or not path.is_file():
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def archive_backtest_artifacts(
    job_id: str,
    result_json: Path,
    summary_json: Path | None,
    run: dict[str, Any],
) -> list[dict[str, Any]]:
    archived = []
    for path in _artifact_paths(job_id, result_json, summary_json, run):
        kind = _artifact_kind(path)
        object_key = f"{job_id}/artifacts/{path.name}"
        if path == result_json:
            object_key = f"{job_id}/result.json"
        elif summary_json and path == summary_json:
            object_key = f"{job_id}/summary.json"
        item = put_file(
            "backtest-results",
            object_key,
            path,
            content_type=_artifact_content_type(path),
            metadata={"job_id": job_id, "kind": kind, "artifact_name": path.name},
        )
        if item:
            archived.append(item)
    return archived


def persist_result(job_id: str, result_json: Path, summary_json: Path | None, run: dict[str, Any]) -> dict[str, Any]:
    payload = parse_result_payload(result_json, summary_json, run)
    artifact_objects = archive_backtest_artifacts(job_id, result_json, summary_json, run)
    raw_object = next(
        (item for item in artifact_objects if item.get("object_key") == f"{job_id}/result.json"),
        {},
    )
    payload["raw_result_object_id"] = raw_object.get("id")
    summary_object = next(
        (
            item
            for item in artifact_objects
            if summary_json and item.get("object_key") == f"{job_id}/summary.json"
        ),
        {},
    )
    if summary_object:
        payload["summary_object_id"] = summary_object.get("id")
    payload.setdefault("performance", {})["artifact_objects"] = [
        {
            "id": item.get("id"),
            "object_key": item.get("object_key"),
            "sha256": item.get("sha256"),
            "size": item.get("size"),
            "kind": (item.get("metadata") or {}).get("kind"),
        }
        for item in artifact_objects
    ]
    return save_result(job_id, payload, utc_now())


def result_for_job(job_id: str) -> dict[str, Any] | None:
    return get_result(job_id)
