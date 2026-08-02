from __future__ import annotations

import hashlib
import json
from typing import Any

from ..db import db, json_dump, row_to_dict, utc_now


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _stable_id(prefix: str, value: Any) -> str:
    return f"{prefix}:{_stable_hash(value)[:32]}"


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def record_experiment_versions(
    *,
    run_id: str,
    project_id: str | None,
    fingerprint: dict[str, Any],
    validation: dict[str, Any],
    experiment: dict[str, Any],
) -> dict[str, Any]:
    now = utc_now()
    strategy = experiment.get("strategy") or {}
    data = experiment.get("data") or {}
    scope = (fingerprint.get("data") or {}).get("scope") or data.get("scope") or {}
    market_daily = data.get("marketDailyBars") or {}
    trade_status = data.get("tradeStatus") or {}
    benchmark = data.get("benchmark") or {}
    strategy_payload = {
        "projectId": project_id,
        "path": strategy.get("path"),
        "sha256": strategy.get("sha256"),
        "gitCommit": strategy.get("gitCommit"),
        "gitStatusHash": strategy.get("gitStatusHash"),
    }
    dataset_payload = {
        "scope": scope,
        "batchId": data.get("batchId"),
        "marketDailyBars": market_daily,
        "tradeStatus": trade_status,
        "benchmark": benchmark,
        "leanZipSha256": data.get("leanZipSha256"),
        "factorFileSha256": data.get("factorFileSha256"),
        "parquetDatasetId": data.get("parquetDatasetId"),
        "parquetFileSha256": data.get("parquetFileSha256"),
    }
    strategy_version_id = _stable_id("strategy", strategy_payload)
    dataset_version_id = _stable_id("dataset", dataset_payload)
    dataset_release_id = fingerprint.get("datasetReleaseId")
    experiment_id = run_id
    with db() as connection:
        existing_run = connection.execute(
            "select dataset_release_id from backtest_runs where id=?",
            (run_id,),
        ).fetchone()
        frozen_release_id = existing_run["dataset_release_id"] if existing_run else None
        if frozen_release_id and dataset_release_id and frozen_release_id != dataset_release_id:
            raise ValueError(
                f"dataset_release_changed_during_run:{frozen_release_id}:{dataset_release_id}"
            )
        dataset_release_id = frozen_release_id or dataset_release_id
        connection.execute(
            """
            insert into strategy_versions
                (id, project_id, strategy_path, source_sha256, git_commit, git_branch, git_dirty,
                 git_status_hash, metadata_json, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(id) do update set
                project_id = excluded.project_id,
                strategy_path = excluded.strategy_path,
                source_sha256 = excluded.source_sha256,
                git_commit = excluded.git_commit,
                git_branch = excluded.git_branch,
                git_dirty = excluded.git_dirty,
                git_status_hash = excluded.git_status_hash,
                metadata_json = excluded.metadata_json
            """,
            (
                strategy_version_id,
                project_id,
                strategy.get("path"),
                strategy.get("sha256"),
                strategy.get("gitCommit"),
                strategy.get("gitBranch"),
                1 if strategy.get("gitDirty") else 0,
                strategy.get("gitStatusHash"),
                json_dump(strategy),
                now,
            ),
        )
        connection.execute(
            """
            insert into dataset_versions
                (id, dataset_key, asset_class, market, venue, resolution, data_type, adjust, symbol,
                 start_date, end_date, row_count, status_count, benchmark_symbol, benchmark_row_count,
                 data_batch_id, lean_zip_sha256, factor_file_sha256, parquet_dataset_id, parquet_file_sha256,
                 metadata_json, created_at, dataset_release_id)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(id) do update set
                row_count = excluded.row_count,
                status_count = excluded.status_count,
                benchmark_row_count = excluded.benchmark_row_count,
                data_batch_id = excluded.data_batch_id,
                lean_zip_sha256 = excluded.lean_zip_sha256,
                factor_file_sha256 = excluded.factor_file_sha256,
                parquet_dataset_id = excluded.parquet_dataset_id,
                parquet_file_sha256 = excluded.parquet_file_sha256,
                metadata_json = excluded.metadata_json,
                dataset_release_id = excluded.dataset_release_id
            """,
            (
                dataset_version_id,
                _stable_hash(scope),
                scope.get("assetClass"),
                scope.get("market"),
                scope.get("venue"),
                scope.get("resolution"),
                scope.get("dataType"),
                scope.get("adjust"),
                scope.get("symbol"),
                scope.get("start"),
                scope.get("end"),
                _int_value(market_daily.get("row_count")),
                _int_value(trade_status.get("row_count")),
                benchmark.get("symbol"),
                _int_value(benchmark.get("row_count")),
                data.get("batchId"),
                data.get("leanZipSha256"),
                data.get("factorFileSha256"),
                data.get("parquetDatasetId"),
                data.get("parquetFileSha256"),
                json_dump(dataset_payload),
                now,
                dataset_release_id,
            ),
        )
        connection.execute(
            "update backtest_runs set dataset_release_id=coalesce(dataset_release_id,?) where id=?",
            (dataset_release_id, run_id),
        )
        connection.execute(
            """
            insert into experiments
                (id, run_id, strategy_version_id, dataset_version_id, parameter_hash, docker_image,
                 docker_image_digest, git_commit, fingerprint_json, validation_json, experiment_json,
                 created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(run_id) do update set
                strategy_version_id = excluded.strategy_version_id,
                dataset_version_id = excluded.dataset_version_id,
                parameter_hash = excluded.parameter_hash,
                docker_image = excluded.docker_image,
                docker_image_digest = excluded.docker_image_digest,
                git_commit = excluded.git_commit,
                fingerprint_json = excluded.fingerprint_json,
                validation_json = excluded.validation_json,
                experiment_json = excluded.experiment_json,
                updated_at = excluded.updated_at
            """,
            (
                experiment_id,
                run_id,
                strategy_version_id,
                dataset_version_id,
                fingerprint.get("parametersHash"),
                fingerprint.get("docker_image"),
                fingerprint.get("docker_image_digest"),
                fingerprint.get("git_commit"),
                json_dump(fingerprint),
                json_dump(validation),
                json_dump(experiment),
                now,
                now,
            ),
        )
    return {
        "experiment_id": experiment_id,
        "strategy_version_id": strategy_version_id,
        "dataset_version_id": dataset_version_id,
    }


def get_experiment_versions(run_id: str) -> dict[str, Any] | None:
    with db() as connection:
        experiment_row = connection.execute("select * from experiments where run_id = ?", (run_id,)).fetchone()
        if experiment_row is None:
            return None
        experiment = row_to_dict(experiment_row) or {}
        strategy = row_to_dict(
            connection.execute("select * from strategy_versions where id = ?", (experiment["strategy_version_id"],)).fetchone()
        )
        dataset = row_to_dict(
            connection.execute("select * from dataset_versions where id = ?", (experiment["dataset_version_id"],)).fetchone()
        )
    return {
        "experiment": experiment,
        "strategyVersion": strategy,
        "datasetVersion": dataset,
    }
