#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
import time
import urllib.error
import urllib.request


TERMINAL_BATCH_STATUSES = {"success", "failed", "partial", "cancelled"}
FOLD_SEPARATORS = ("-", "_", ".")
ROOT = Path(__file__).resolve().parents[1]


def _api_token() -> str:
    configured = os.environ.get("LEAN_API_TOKEN", "").strip()
    if configured:
        return configured
    token_path = Path(
        os.environ.get(
            "LEAN_API_TOKEN_FILE",
            str(ROOT / "web" / "runtime" / "secrets" / "api_token"),
        )
    )
    try:
        return token_path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _api_headers(*, json_content: bool = False) -> dict[str, str]:
    headers = {"Content-Type": "application/json"} if json_content else {}
    token = _api_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _to_int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(_safe_str(value)[:10])
    except ValueError:
        return None


def _parse_fold(value: Any) -> int | None:
    text = _safe_str(value).strip()
    if not text:
        return None
    for sep in FOLD_SEPARATORS:
        if sep in text:
            text = text.split(sep)[0]
            break
    return _to_int_or_none(text)


def _normalize(value: Any) -> str:
    return _safe_str(value).strip().lower()


def _is_truthy(value: Any) -> bool:
    text = _safe_str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "on"}


@dataclass
class ApiFailure(RuntimeError):
    status: int
    payload: Any
    path: str


def _api(
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: int = 300,
) -> tuple[Any, int, dict[str, str]]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        headers=_api_headers(json_content=True),
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            body: Any = json.loads(raw) if raw else {}
            headers = {key.lower(): value for key, value in response.headers.items()}
            return body, response.status, headers
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload_obj: Any = json.loads(raw)
        except json.JSONDecodeError:
            payload_obj = {"detail": raw}
        raise ApiFailure(exc.code, payload_obj, path) from exc


def _poll_batch(base_url: str, batch_id: str, *, timeout_seconds: int, poll_seconds: float = 2.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_detail: dict[str, Any] = {}
    last_status = "queued"
    while time.monotonic() < deadline:
        detail, _, _ = _api(base_url, "GET", f"/api/experiment-batches/{batch_id}")
        last_detail = detail
        status = _safe_str(detail.get("status") or "queued").lower()
        last_status = status
        if status in TERMINAL_BATCH_STATUSES:
            return detail
        time.sleep(max(0.25, poll_seconds))
    raise TimeoutError(f"experiment_batch_timeout:{batch_id}:{last_status}:{timeout_seconds}")


def _fetch_csv_preview(base_url: str, batch_id: str) -> dict[str, Any]:
    path = f"/api/experiment-batches/{batch_id}/export.csv"
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        headers=_api_headers(),
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read().decode("utf-8")
    lines = [line for line in raw.splitlines() if line.strip()]
    if not lines:
        return {"hasCsv": False}
    reader = csv.DictReader(lines)
    rows = list(reader)
    return {
        "hasCsv": True,
        "lineCount": len(lines),
        "dataRows": max(0, len(rows)),
        "header": reader.fieldnames or [],
        "preview": rows[:3],
    }


def _item_parameters(item: dict[str, Any]) -> dict[str, Any]:
    params = item.get("parameters")
    return params if isinstance(params, dict) else {}


def _item_experiment_param(item: dict[str, Any], key: str, *, fallback: str = "") -> str:
    params = _item_parameters(item)
    return _safe_str(params.get(key, params.get("parameters", {}).get(key, fallback))).strip()


def _item_window(item: dict[str, Any]) -> tuple[str, str]:
    params = _item_parameters(item)
    return _safe_str(params.get("start") or item.get("start") or ""), _safe_str(params.get("end") or item.get("end") or "")


def _window_tuple(item: dict[str, Any]) -> tuple[date | None, date | None, str, str]:
    start, end = _item_window(item)
    return _to_date(start), _to_date(end), start, end


def _candidate_key(item: dict[str, Any]) -> str:
    return _item_experiment_param(
        item,
        "optimizationCandidateKey",
        fallback=_item_experiment_param(item, "candidateKey", fallback="base"),
    )


def _item_bucket(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _safe_str(item.get("projectId") or item.get("project_id") or ""),
        _safe_str(item.get("symbol") or ""),
        _candidate_key(item),
    )


def _validate_rolling(
    items: list[dict[str, Any]],
    config: dict[str, Any],
    failures: list[str],
    warnings: list[str],
    min_folds: int,
) -> None:
    grouped: dict[tuple[tuple[str, str, str], int], list[dict[str, Any]]] = defaultdict(list)
    modes: set[str] = set()

    for item in items:
        fold = _parse_fold(_item_experiment_param(item, "experimentFold", fallback="0")) or 0
        phase = _normalize(_item_experiment_param(item, "experimentPhase"))
        modes.add(_normalize(_item_experiment_param(item, "experimentMode")))
        if fold > 0:
            grouped[(_item_bucket(item), fold)].append({**item, "_phase": phase})

        start_d, end_d, start_text, end_text = _window_tuple(item)
        if not start_d or not end_d:
            warnings.append(f"rolling_invalid_window_format:{start_text}:{end_text}")
            continue
        if end_d < start_d:
            failures.append(f"rolling_window_reversed:{start_text}:{end_text}")

    if not grouped:
        failures.append("rolling_missing_folds")
        return

    folds = sorted({fold for *_, fold in grouped})
    if folds:
        expected = list(range(min(folds), max(folds) + 1))
        missing = sorted(set(expected) - set(folds))
        if missing:
            failures.append(f"rolling_fold_gap:{missing}")

    if len(folds) < max(1, min_folds):
        failures.append(f"rolling_folds_below_min:{len(folds)}:{max(1, min_folds)}")

    for group_key, group_items in grouped.items():
        bucket, fold = group_key
        phase_set = {item.get("_phase", "") for item in group_items}
        if phase_set != {"rolling"}:
            failures.append(f"rolling_phase_mismatch:{bucket}:{fold}:{sorted(phase_set)}")

    if not modes or not any(mode == "rolling" for mode in modes):
        failures.append("rolling_mode_not_marked")

    # In rolling mode, each fold should map to a single bucketed window per project/symbol/candidate.
    for group_key, group_items in grouped.items():
        if len(group_items) != 1:
            warnings.append(f"rolling_multiple_windows_in_bucket:{group_key}:{len(group_items)}")

    windows_by_fold: dict[int, tuple[date, date]] = {}
    for (_, fold), gitems in grouped.items():
        if len(gitems) == 1:
            start_d, end_d, _, _ = _window_tuple(gitems[0])
            if start_d and end_d:
                windows_by_fold[fold] = (start_d, end_d)

    ordered_folds = sorted(windows_by_fold)
    for prev_fold, next_fold in zip(ordered_folds, ordered_folds[1:]):
        prev_end = windows_by_fold[prev_fold][1]
        next_start = windows_by_fold[next_fold][0]
        if next_start and prev_end and next_start < prev_end:
            warnings.append(f"rolling_window_overlaps_or_rollback:{prev_fold}:{next_fold}:{prev_end}:{next_start}")

    expected_mode = _normalize(config.get("mode"))
    if expected_mode and expected_mode not in modes:
        failures.append(f"rolling_mode_mismatch:{expected_mode}:{sorted(modes)}")


def _validate_walk_forward(
    items: list[dict[str, Any]],
    config: dict[str, Any],
    failures: list[str],
    warnings: list[str],
    min_folds: int,
) -> None:
    grouped: dict[tuple[int, tuple[str, str, str]], list[dict[str, Any]]] = defaultdict(list)
    modes: set[str] = set()
    for item in items:
        fold = _parse_fold(_item_experiment_param(item, "experimentFold", fallback="0")) or 0
        phase = _normalize(_item_experiment_param(item, "experimentPhase"))
        modes.add(_normalize(_item_experiment_param(item, "experimentMode")))
        if fold > 0:
            grouped[(fold, _item_bucket(item))].append({**item, "_phase": phase})

        start_d, end_d, start_text, end_text = _window_tuple(item)
        if not start_d or not end_d:
            warnings.append(f"walk_forward_invalid_window_format:{start_text}:{end_text}")
            continue
        if end_d < start_d:
            failures.append(f"walk_forward_window_reversed:{start_text}:{end_text}")

    if not grouped:
        failures.append("walk_forward_missing_folds")
        return

    folds = sorted({fold for fold, _ in grouped})
    expected_fold_range = list(range(min(folds), max(folds) + 1))
    missing_folds = sorted(set(expected_fold_range) - set(folds))
    if missing_folds:
        failures.append(f"walk_forward_fold_gap:{missing_folds}")
    if len(folds) < max(1, min_folds):
        failures.append(f"walk_forward_folds_below_min:{len(folds)}:{max(1, min_folds)}")

    summary = (config.get("trainYears"), config.get("testYears"), config.get("stepYears"))
    if not all(_to_int_or_none(value) for value in summary):
        warnings.append("walk_forward_param_parse_warning")

    if not modes or not any(mode == "walk_forward" for mode in modes):
        failures.append("walk_forward_mode_not_marked")

    for (fold, _bucket), fold_items in grouped.items():
        phases = {_safe_str(item.get("_phase")) for item in fold_items}
        if phases != {"train", "validation", "oos"}:
            failures.append(f"walk_forward_fold_phase_invalid:{fold}:{sorted(phases)}")
            continue

        by_phase: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in fold_items:
            by_phase[_safe_str(item.get("_phase"))].append(item)

        if any(len(by_phase[phase]) != 1 for phase in ("train", "validation", "oos")):
            failures.append(
                "walk_forward_phase_multiplicity:"
                f"{fold}:train={len(by_phase['train'])},"
                f"validation={len(by_phase['validation'])},oos={len(by_phase['oos'])}"
            )
            continue

        train_start, train_end, _, _ = _window_tuple(by_phase["train"][0])
        validation_start, validation_end, _, _ = _window_tuple(by_phase["validation"][0])
        oos_start, oos_end, _, _ = _window_tuple(by_phase["oos"][0])
        if not all((train_start, train_end, validation_start, validation_end, oos_start, oos_end)):
            continue
        if train_end >= validation_start:
            failures.append(
                f"walk_forward_train_validation_nonsequential:{fold}:"
                f"{train_start}:{train_end}:{validation_start}:{validation_end}"
            )
        if validation_end >= oos_start:
            failures.append(
                f"walk_forward_validation_oos_nonsequential:{fold}:"
                f"{validation_start}:{validation_end}:{oos_start}:{oos_end}"
            )
        if validation_end < validation_start:
            failures.append(f"walk_forward_validation_window_reversed:{fold}")
        if oos_end < oos_start:
            failures.append(f"walk_forward_oos_window_reversed:{fold}")

    summary_payload = (config.get("summary") or {})
    walk_forward_summary = summary_payload.get("walkForward") if isinstance(summary_payload, dict) else None
    if isinstance(walk_forward_summary, list):
        summary_folds = {entry.get("fold") for entry in walk_forward_summary if isinstance(entry, dict)}
        missing_summary = sorted(set(folds) - summary_folds)
        if missing_summary:
            warnings.append(f"walk_forward_summary_fold_gap:{missing_summary}")


def _validate_dynamic_pit(
    items: list[dict[str, Any]],
    config: dict[str, Any],
    detail: dict[str, Any],
    failures: list[str],
    warnings: list[str],
) -> None:
    config = dict(config)
    resolved = (detail.get("config") or {}).get("resolvedSelection") or {}
    if _safe_str(resolved.get("type") or "").lower() != "universe":
        failures.append("dynamic_selection_not_universe")

    expected_code = _safe_str(config.get("universeCode") or resolved.get("universeCode")).upper()
    resolved_code = _safe_str(resolved.get("universeCode")).upper()
    if expected_code and resolved_code and expected_code != resolved_code:
        failures.append(f"dynamic_universe_code_mismatch:{expected_code}:{resolved_code}")

    symbols = resolved.get("symbols") or []
    if not isinstance(symbols, list) or not symbols:
        failures.append("dynamic_universe_no_symbols")
    symbol_set = {str(item).upper() for item in symbols if str(item).strip()}
    if not symbol_set:
        warnings.append("dynamic_universe_symbol_set_empty_after_normalize")

    config_start = _safe_str(config.get("start") or "").strip()
    config_end = _safe_str(config.get("end") or "").strip()
    config_start_date = _to_date(config_start)
    config_end_date = _to_date(config_end)

    schedules: list[dict[str, Any]] = []
    missing_schedule_items = 0
    non_dict_rows = 0
    for item in items:
        params = _item_parameters(item)
        strategy_params = params.get("parameters")
        strategy_params = strategy_params if isinstance(strategy_params, dict) else {}
        universe_code = params.get("universeCode", strategy_params.get("universeCode"))
        if _safe_str(universe_code).upper() != expected_code:
            warnings.append(f"dynamic_universe_code_skew_item:{universe_code}")
        dynamic_universe = params.get("dynamicUniverse", strategy_params.get("dynamicUniverse"))
        if _normalize(dynamic_universe) not in {"true", "1"}:
            failures.append("dynamic_universe_flag_not_true")
            break

        schedule = params.get("universeSchedule", strategy_params.get("universeSchedule"))
        if not schedule:
            missing_schedule_items += 1
            continue

        try:
            parsed = json.loads(schedule) if isinstance(schedule, str) else schedule
        except Exception:
            failures.append("dynamic_universe_schedule_invalid_json")
            continue
        if not isinstance(parsed, list) or not parsed:
            missing_schedule_items += 1
            continue
        schedules.extend([entry for entry in parsed if entry])

    if not schedules and missing_schedule_items >= len(items):
        failures.append("dynamic_universe_no_schedule_rows")

    normalized_rows: list[tuple[str, date | None, date | None]] = []
    for index, entry in enumerate(schedules):
        if not isinstance(entry, dict):
            non_dict_rows += 1
            continue
        symbol = _safe_str(entry.get("symbol") or entry.get("code")).upper()
        if not symbol:
            failures.append(f"dynamic_universe_schedule_row_symbol_missing:{index}")
            continue
        if symbol not in symbol_set:
            warnings.append(f"dynamic_universe_schedule_unknown_symbol:{symbol}")

        start_date = _to_date(entry.get("startDate") or entry.get("start_date"))
        end_date = _to_date(entry.get("endDate") or entry.get("end_date"))
        if not start_date:
            failures.append(f"dynamic_universe_schedule_row_start_missing:{index}:{symbol}")
            continue
        if end_date and end_date < start_date:
            failures.append(f"dynamic_universe_schedule_row_window_reversed:{index}:{symbol}:{start_date}:{end_date}")
        normalized_rows.append((symbol, start_date, end_date))

    if missing_schedule_items:
        failures.append(f"dynamic_universe_missing_schedule:{missing_schedule_items}")
    if non_dict_rows:
        failures.append(f"dynamic_universe_schedule_non_dict:{non_dict_rows}")

    # Validate schedule coverage plausibility for requested window.
    if not failures and config_start_date and config_end_date and normalized_rows:
        has_cover = False
        for symbol, start_d, end_d in normalized_rows:
            if start_d > config_end_date:
                continue
            if end_d is None or end_d >= config_start_date:
                has_cover = True
                break
        if not has_cover:
            failures.append("dynamic_universe_no_schedule_covers_request")

    summary = detail.get("summary") if isinstance(detail.get("summary"), dict) else {}
    if isinstance(summary, dict):
        if summary.get("rankingMetric") and not isinstance(summary.get("ranking"), list):
            failures.append("dynamic_universe_summary_ranking_format")


def _validate_item_keys(items: list[dict[str, Any]], failures: list[str], warnings: list[str]) -> None:
    keys = [_safe_str(item.get("item_key") or item.get("key") or item.get("id")) for item in items]
    empty = [k for k in keys if not k]
    if empty:
        failures.append(f"item_key_missing:{len(empty)}")
    duplicates = [k for k in set(keys) if k and keys.count(k) > 1]
    if duplicates:
        failures.append(f"item_key_duplicates:{sorted(duplicates)}")
    if len(keys) > 10000:
        warnings.append(f"large_batch_item_count:{len(keys)}")


def _validate_status_counts(items: list[dict[str, Any]], failures: list[str], warnings: list[str]) -> None:
    valid_statuses = {"pending", "queued", "dispatching", "running", "success", "failed", "skipped", "cancelled"}
    invalid = sorted({
        _safe_str(item.get("status") or "")
        for item in items
        if _safe_str(item.get("status") or "") and _safe_str(item.get("status") or "") not in valid_statuses
    })
    if invalid:
        failures.append(f"unexpected_item_status:{invalid}")
    failed_count = sum(1 for item in items if _safe_str(item.get("status") or "") == "failed")
    if failed_count > 0:
        failures.append(f"failed_items:{failed_count}")


def _validate_parameter_grid(
    items: list[dict[str, Any]],
    config: dict[str, Any],
    failures: list[str],
    warnings: list[str],
) -> None:
    grid = config.get("parameterGrid") or {}
    expected = 1
    for values in grid.values():
        expected *= len(values or [])
    if expected != 9:
        failures.append(f"parameter_grid_not_3x3:{expected}")
    if len(items) != expected:
        failures.append(f"parameter_grid_item_count:{len(items)}:{expected}")
    candidates = {
        _item_experiment_param(item, "optimizationCandidateKey")
        for item in items
    }
    candidates.discard("")
    if len(candidates) != expected:
        failures.append(f"parameter_grid_candidate_keys:{len(candidates)}:{expected}")
    if any(item.get("status") == "success" and not item.get("related_id") for item in items):
        warnings.append("successful_grid_item_missing_related_run")


def _validate_case_result(name: str, config: dict[str, Any], detail: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    mode = str(config.get("mode") or "independent").strip().lower()
    warnings: list[str] = []
    failures: list[str] = []

    status = _normalize(detail.get("status") or "")
    if status != "success":
        failures.append(f"batch_status_not_success:{status}")

    items = list(detail.get("items") or [])
    if not items:
        failures.append("items_empty")
        return "failed", warnings, failures

    _validate_item_keys(items, failures, warnings)
    _validate_status_counts(items, failures, warnings)

    min_rolling_folds = int(config.get("minRollingFolds") or 1) if mode == "rolling" else 1
    min_walk_folds = int(config.get("minWalkForwardFolds") or 1) if mode == "walk_forward" else 1

    if name == "parameter_grid":
        _validate_parameter_grid(items, config, failures, warnings)
    elif mode == "rolling":
        _validate_rolling(items, config, failures, warnings, min_folds=min_rolling_folds)
    elif mode == "walk_forward":
        _validate_walk_forward(items, config, failures, warnings, min_folds=min_walk_folds)
    elif mode == "dynamic_universe":
        _validate_dynamic_pit(items, config, detail, failures, warnings)

    summary = detail.get("summary")
    if isinstance(summary, dict):
        runs = summary.get("runs")
        if _to_int(runs, default=0) == 0:
            warnings.append("summary_runs_zero")

    count_from_detail = len(items)
    count_from_preview = _to_int((detail.get("total") or detail.get("count") or detail.get("queued") or 0), default=None)
    if count_from_preview is not None and count_from_preview != count_from_detail:
        warnings.append(f"item_count_mismatch:{count_from_preview}:{count_from_detail}")

    return ("failed" if failures else "passed"), warnings, failures


def _run_case(
    base_url: str,
    case_name: str,
    config: dict[str, Any],
    *,
    execute: bool,
    timeout: int,
    poll_seconds: float,
    require_csv: bool,
) -> dict[str, Any]:
    preview, _, _ = _api(base_url, "POST", "/api/experiment-batches/preview", config)
    preview_within_limit = bool(preview.get("withinLimit", False))
    preview_expanded = preview.get("expandedCount")
    result: dict[str, Any] = {
        "case": case_name,
        "preview": {
            "expandedCount": preview_expanded,
            "withinLimit": preview_within_limit,
            "limit": preview.get("limit"),
            "mode": preview.get("mode"),
            "kind": preview.get("kind"),
            "selection": preview.get("selection"),
            "sample": (preview.get("sample") or [])[:3],
            "warnings": preview.get("warnings") or [],
        },
    }

    if not preview_within_limit:
        result["status"] = "failed"
        result["error"] = "preview_exceeds_limit"
        result["errorDetail"] = preview
        return result

    if not execute:
        result["status"] = "preview-only"
        return result

    created = _api(base_url, "POST", "/api/experiment-batches", config)[0]
    batch_id = _safe_str(created.get("id"))
    if not batch_id:
        raise RuntimeError(f"{case_name}: create batch returned no id")

    result["batchId"] = batch_id
    detail = _poll_batch(base_url, batch_id, timeout_seconds=timeout, poll_seconds=poll_seconds)
    result["detail"] = detail

    items = list(detail.get("items") or [])
    result["itemCount"] = len(items)
    result["statusCounts"] = {
        "success": sum(1 for item in items if _safe_str(item.get("status")) == "success"),
        "failed": sum(1 for item in items if _safe_str(item.get("status")) == "failed"),
        "pending": sum(1 for item in items if _safe_str(item.get("status")) == "pending"),
        "queued": sum(1 for item in items if _safe_str(item.get("status")) == "queued"),
        "running": sum(1 for item in items if _safe_str(item.get("status")) == "running"),
        "skipped": sum(1 for item in items if _safe_str(item.get("status")) == "skipped"),
    }

    mode_status, mode_warnings, mode_failures = _validate_case_result(case_name, config, detail)
    result["validation"] = {
        "status": mode_status,
        "warnings": mode_warnings,
        "failures": mode_failures,
    }
    result["status"] = mode_status
    result["warnings"] = list(preview.get("warnings") or [])
    result["warnings"].extend(mode_warnings)

    csv_report = _fetch_csv_preview(base_url, batch_id)
    result["csv"] = csv_report
    if require_csv and not csv_report.get("hasCsv"):
        result["status"] = "failed"
        result["error"] = "csv_export_missing"
        result["errorDetail"] = csv_report
    if result["status"] == "failed":
        result["failedReason"] = mode_failures

    batch_total = _to_int(detail.get("total"), default=None)
    if batch_total is not None and batch_total != len(items):
        result["warnings"].append(f"detail_total_mismatch:{batch_total}:{len(items)}")
    return result


def _build_configs(project_id: str) -> dict[str, dict[str, Any]]:
    return {
        "parameter_grid": {
            "kind": "backtest",
            "mode": "single_symbol_grid",
            "projectIds": [project_id],
            "symbol": "600519",
            "assetClass": "equity",
            "market": "china",
            "venue": "china",
            "resolution": "daily",
            "dataType": "trade",
            "cash": 300000,
            "start": "2023-01-03",
            "end": "2023-06-30",
            "source": "tushare",
            "maxCandidates": 9,
            "parameterGrid": {
                "fast": [5, 10, 15],
                "slow": [20, 30, 40],
            },
        },
        "rolling": {
            "kind": "backtest",
            "mode": "rolling",
            "projectIds": [project_id],
            "symbol": "600519",
            "assetClass": "equity",
            "market": "china",
            "venue": "china",
            "resolution": "daily",
            "dataType": "trade",
            "cash": 300000,
            "start": "2022-01-01",
            "end": "2024-12-31",
            "trainYears": 1,
            "testYears": 1,
            "stepYears": 1,
            "source": "tushare",
            "maxCandidates": 9,
            "parameterGrid": {
                "fast": [5, 10, 15],
                "slow": [20, 30, 40],
            },
            "minRollingFolds": 3,
        },
        "walk_forward": {
            "kind": "backtest",
            "mode": "walk_forward",
            "projectIds": [project_id],
            "symbol": "600519",
            "assetClass": "equity",
            "market": "china",
            "venue": "china",
            "resolution": "daily",
            "dataType": "trade",
            "cash": 300000,
            "start": "2023-01-01",
            "end": "2025-12-31",
            "trainYears": 1,
            "testYears": 1,
            "stepYears": 1,
            "source": "tushare",
            "maxCandidates": 1,
            "parameterGrid": {
                "fast": [10],
            },
            "minWalkForwardFolds": 2,
        },
        "dynamic_pit": {
            "kind": "backtest",
            "mode": "dynamic_universe",
            "projectIds": [project_id],
            "universeCode": "CSI300",
            "assetClass": "equity",
            "market": "china",
            "venue": "china",
            "resolution": "daily",
            "dataType": "trade",
            "cash": 300000,
            "start": "2021-01-01",
            "end": "2021-12-31",
            "source": "tushare",
            "maxCandidates": 1,
            "parameterGrid": {},
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Level-4 evidence probes for grid/rolling/walk-forward/dynamic PIT")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    preview_group = parser.add_mutually_exclusive_group()
    preview_group.add_argument("--execute", action="store_true", help="Create and run batches instead of preview-only")
    preview_group.add_argument(
        "--preview-only",
        action="store_true",
        help="Force preview-only mode (same as default without --execute).",
    )
    parser.add_argument("--require-csv", action="store_true", help="Fail if export.csv is missing or empty when executing")
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--cases", default="parameter_grid,rolling,walk_forward,dynamic_pit", help="Comma-separated case names")
    parser.add_argument("--evidence-out", help="Write full JSON evidence to this file")
    parser.add_argument("--min-rolling-folds", type=int, default=1)
    parser.add_argument("--min-walk-forward-folds", type=int, default=2)
    args = parser.parse_args()

    selected = {name.strip() for name in args.cases.split(",") if name.strip()}
    available = _build_configs(args.project_id)
    unknown = sorted(selected - set(available))
    if unknown:
        raise SystemExit(f"Unknown cases: {unknown}")

    configs = {name: available[name] for name in available if name in selected}
    for case_name, case in configs.items():
        if case_name == "rolling":
            case["minRollingFolds"] = max(1, args.min_rolling_folds)
        if case_name == "walk_forward":
            case["minWalkForwardFolds"] = max(1, args.min_walk_forward_folds)

    summary: dict[str, Any] = {
        "baseUrl": args.base_url,
        "projectId": args.project_id,
        "runMode": "execute" if args.execute else "preview",
        "cases": {},
    }

    failures = 0
    for name, config in configs.items():
        print(f"[LEVEL4] {name} ...", flush=True)
        try:
            case_result = _run_case(
                args.base_url,
                name,
                config,
                execute=args.execute,
                timeout=args.timeout,
                poll_seconds=args.poll_seconds,
                require_csv=args.require_csv,
            )
            summary["cases"][name] = case_result
            if case_result.get("status") not in {"passed", "preview-only"}:
                failures += 1
        except ApiFailure as exc:
            failures += 1
            summary["cases"][name] = {
                "case": name,
                "status": "failed",
                "error": f"api_{exc.status}:{exc.path}:{exc.payload}",
            }
            print(f"[LEVEL4] {name} failed: api_{exc.status} {exc.path}", flush=True)
        except Exception as exc:
            failures += 1
            summary["cases"][name] = {
                "case": name,
                "status": "failed",
                "error": str(exc),
            }
            print(f"[LEVEL4] {name} failed: {exc}", flush=True)

    summary["failures"] = failures
    summary["passed"] = failures == 0
    print(json.dumps({"status": "passed" if summary["passed"] else "failed", "failures": failures}, ensure_ascii=False))
    if args.evidence_out:
        target = Path(args.evidence_out).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return 0 if summary["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
