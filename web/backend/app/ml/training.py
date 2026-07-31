from __future__ import annotations

import json
import math
import os
import statistics
import uuid
from pathlib import Path
from typing import Any, Callable, Sequence

import polars as pl

from ..db import db, json_dump, utc_now
from .cross_sectional import FEATURE_COLUMNS, candidate_grid, prediction_metrics


MODEL_NAME = "lean-ashare-csi300-lgbm-ranker"


def _set_progress(training_id: str, progress: float, stage: str) -> None:
    with db() as connection:
        connection.execute(
            "update ml_training_runs set progress=?,stage=?,updated_at=? where id=?",
            (progress, stage, utc_now(), training_id),
        )


def final_training_dates(
    pre_holdout_dates: Sequence[Any], *, purge_days: int = 5, maximum_days: int = 252 * 5,
) -> list[Any]:
    ordered = sorted(set(pre_holdout_dates))
    if len(ordered) <= purge_days:
        raise ValueError("Final holdout purging leaves no training dates.")
    eligible = ordered[:-purge_days]
    return eligible[-maximum_days:]


def _rank_frame(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.sort(["trade_date", "symbol"])


def _groups(frame: pl.DataFrame) -> list[int]:
    return frame.group_by("trade_date", maintain_order=True).len()["len"].to_list()


def _matrix(frame: pl.DataFrame):
    return frame.select(FEATURE_COLUMNS).to_numpy()


def _ndcg(items: list[dict[str, Any]], k: int) -> float | None:
    if not items:
        return None

    def dcg(values: list[int]) -> float:
        return sum((2 ** value - 1) / math.log2(index + 2) for index, value in enumerate(values[:k]))

    ranked = [int(item["relevance"]) for item in sorted(items, key=lambda item: float(item["score"]), reverse=True)]
    ideal = sorted((int(item["relevance"]) for item in items), reverse=True)
    denominator = dcg(ideal)
    return None if denominator <= 0 else dcg(ranked) / denominator


def _extended_metrics(frame: pl.DataFrame, scores) -> dict[str, Any]:
    rows = frame.select("trade_date", "symbol", "label_return", "relevance").with_columns(
        pl.Series("score", scores)
    ).to_dicts()
    metrics = prediction_metrics(rows)
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_date.setdefault(str(row["trade_date"]), []).append(row)
    for k in (10, 30):
        values = [value for value in (_ndcg(items, k) for items in by_date.values()) if value is not None]
        metrics[f"ndcgAt{k}"] = statistics.fmean(values) if values else None
    precision = []
    for items in by_date.values():
        top = sorted(items, key=lambda item: float(item["score"]), reverse=True)[:30]
        if top:
            precision.append(sum(int(item["relevance"]) == 4 for item in top) / len(top))
    metrics["precisionAt30"] = statistics.fmean(precision) if precision else None
    return metrics


def _model(parameters: dict[str, Any], *, n_estimators: int = 2000):
    import lightgbm as lgb

    return lgb.LGBMRanker(
        objective="lambdarank", label_gain=[0, 1, 3, 7, 15], eval_at=[10, 30],
        n_estimators=n_estimators, deterministic=True, force_col_wise=True,
        random_state=20260731, n_jobs=max(1, int(os.environ.get("LEAN_ML_THREADS", "4"))),
        verbosity=-1, **parameters,
    )


def _fit_candidate(train: pl.DataFrame, validation: pl.DataFrame, parameters: dict[str, Any]):
    import lightgbm as lgb

    model = _model(parameters)
    model.fit(
        _matrix(train), train["relevance"].to_numpy(), group=_groups(train),
        eval_set=[(_matrix(validation), validation["relevance"].to_numpy())],
        eval_group=[_groups(validation)], eval_at=[10, 30],
        callbacks=[lgb.early_stopping(100, verbose=False)],
    )
    return model


def _record_trial(
    training_id: str, fold_index: int, candidate_index: int, parameters: dict[str, Any],
    metrics: dict[str, Any], best_iteration: int, mlflow_run_id: str | None,
) -> str:
    trial_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"ml-trial:{training_id}:{fold_index}:{candidate_index}"))
    with db() as connection:
        connection.execute(
            """insert into ml_training_trials
               (id,training_run_id,fold_index,candidate_index,status,parameters_json,metrics_json,
                best_iteration,mlflow_run_id,selected,created_at,finished_at)
               values (?,?,?,?,'success',?,?,?,?,0,?,?)
               on conflict(training_run_id,fold_index,candidate_index) do update set
                 status='success',parameters_json=excluded.parameters_json,metrics_json=excluded.metrics_json,
                 best_iteration=excluded.best_iteration,mlflow_run_id=excluded.mlflow_run_id,
                 finished_at=excluded.finished_at""",
            (trial_id, training_id, fold_index, candidate_index, json_dump(parameters), json_dump(metrics),
             best_iteration, mlflow_run_id, utc_now(), utc_now()),
        )
    return trial_id


def _write_predictions(
    training_id: str, split_key: str, frame: pl.DataFrame, scores, root: Path, metrics: dict[str, Any],
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"predictions-{split_key}.parquet"
    output = frame.select("trade_date", "symbol", "label_return", "relevance").with_columns(pl.Series("score", scores))
    output.write_parquet(path, compression="zstd")
    import hashlib
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    file_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"ml-predictions:{training_id}:{split_key}"))
    with db() as connection:
        connection.execute(
            """insert into ml_prediction_files
               (id,training_run_id,split_key,relative_path,sha256,row_count,metrics_json,created_at)
               values (?,?,?,?,?,?,?,?)
               on conflict(training_run_id,split_key) do update set relative_path=excluded.relative_path,
                 sha256=excluded.sha256,row_count=excluded.row_count,metrics_json=excluded.metrics_json""",
            (file_id, training_id, split_key, str(path), digest, output.height, json_dump(metrics), utc_now()),
        )
    return path


def train_ranker(
    *, training_id: str, feature_path: Path, fold_plan: dict[str, Any], artifact_root: Path,
    log: Callable[[str], None], cancelled: Callable[[], bool],
) -> dict[str, Any]:
    import lightgbm as lgb
    import mlflow
    import mlflow.lightgbm

    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000")
    experiment_name = os.environ.get("LEAN_MLFLOW_EXPERIMENT", "lean-ashare-cross-sectional")
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name)
    panel = _rank_frame(pl.read_parquet(feature_path))
    candidates = candidate_grid()
    candidate_results: dict[int, list[dict[str, Any]]] = {index: [] for index in range(len(candidates))}
    best_iterations: dict[int, list[int]] = {index: [] for index in range(len(candidates))}
    parent_name = f"csi300-ranker-{training_id}"
    with mlflow.start_run(run_name=parent_name) as parent:
        parent_run_id = parent.info.run_id
        parent_experiment_id = parent.info.experiment_id
        mlflow.set_tags({"research_type": "cross_sectional_ranker", "deployment_status": "research_only", "training_run_id": training_id})
        mlflow.log_params({"feature_version": "csi300-lgbm-ranker-v1", "candidate_count": len(candidates), "fold_count": len(fold_plan["folds"])})
        for fold in fold_plan["folds"]:
            if cancelled():
                raise InterruptedError("ML research was cancelled.")
            train = panel.filter((pl.col("trade_date") >= fold["trainStart"]) & (pl.col("trade_date") <= fold["trainEnd"]))
            validation = panel.filter((pl.col("trade_date") >= fold["validationStart"]) & (pl.col("trade_date") <= fold["validationEnd"]))
            if train.is_empty() or validation.is_empty():
                raise ValueError(f"Fold {fold['index']} has an empty train or validation split.")
            log(f"Training fold {fold['index'] + 1}/{len(fold_plan['folds'])}: {len(candidates)} fixed candidates.")
            for candidate_index, parameters in enumerate(candidates):
                with mlflow.start_run(run_name=f"fold-{fold['index']}-candidate-{candidate_index}", nested=True) as child:
                    mlflow.log_params({**parameters, "fold_index": fold["index"]})
                    model = _fit_candidate(train, validation, parameters)
                    scores = model.predict(_matrix(validation), num_iteration=model.best_iteration_)
                    metrics = _extended_metrics(validation, scores)
                    for key, value in metrics.items():
                        if isinstance(value, (int, float)) and value is not None:
                            mlflow.log_metric(key, float(value))
                    candidate_results[candidate_index].append(metrics)
                    best_iterations[candidate_index].append(int(model.best_iteration_ or 2000))
                    _record_trial(training_id, fold["index"], candidate_index, parameters, metrics, int(model.best_iteration_ or 2000), child.info.run_id)
            _set_progress(
                training_id,
                0.25 + 0.45 * (fold["index"] + 1) / len(fold_plan["folds"]),
                f"candidate_search_fold_{fold['index'] + 1}",
            )
        ranked_candidates = []
        for index, metrics_list in candidate_results.items():
            rank_ics = [item["meanRankIc"] for item in metrics_list if item.get("meanRankIc") is not None]
            ndcgs = [item["ndcgAt30"] for item in metrics_list if item.get("ndcgAt30") is not None]
            ranked_candidates.append((
                statistics.fmean(rank_ics) if rank_ics else -1.0,
                statistics.fmean(ndcgs) if ndcgs else -1.0,
                -int(candidates[index]["num_leaves"]), int(candidates[index]["min_child_samples"]), index,
            ))
        selected_index = max(ranked_candidates)[-1]
        selected_parameters = candidates[selected_index]
        selected_rounds = max(1, int(statistics.median(best_iterations[selected_index])))
        with db() as connection:
            connection.execute(
                "update ml_training_trials set selected=1 where training_run_id=? and candidate_index=?",
                (training_id, selected_index),
            )
        log(f"Selected candidate {selected_index} with {selected_rounds} median boosting rounds.")
        _set_progress(training_id, 0.72, "rolling_oos")
        oos_frames = []
        oos_scores: list[float] = []
        for fold in fold_plan["folds"]:
            if cancelled():
                raise InterruptedError("ML research was cancelled.")
            train = panel.filter((pl.col("trade_date") >= fold["trainStart"]) & (pl.col("trade_date") <= fold["validationEnd"]))
            test = panel.filter((pl.col("trade_date") >= fold["testStart"]) & (pl.col("trade_date") <= fold["testEnd"]))
            model = _model(selected_parameters, n_estimators=selected_rounds)
            model.fit(_matrix(train), train["relevance"].to_numpy(), group=_groups(train))
            scores = model.predict(_matrix(test))
            oos_frames.append(test)
            oos_scores.extend(float(value) for value in scores)
        oos = pl.concat(oos_frames, how="vertical_relaxed")
        rolling_metrics = _extended_metrics(oos, oos_scores)
        oos_path = _write_predictions(training_id, "rolling-oos", oos, oos_scores, artifact_root, rolling_metrics)
        _set_progress(training_id, 0.86, "final_holdout")
        holdout = fold_plan["holdout"]
        holdout_frame = panel.filter((pl.col("trade_date") >= holdout["start"]) & (pl.col("trade_date") <= holdout["end"]))
        pre_holdout = panel.filter(pl.col("trade_date") < holdout["start"])
        pre_dates = pre_holdout["trade_date"].unique().sort().to_list()
        purge_days = int(fold_plan.get("purgeTradingDays") or 5)
        if holdout_frame.is_empty():
            raise ValueError("Final holdout or its purged training history is empty.")
        eligible_dates = final_training_dates(pre_dates, purge_days=purge_days)
        pre_holdout = pre_holdout.filter(
            (pl.col("trade_date") >= eligible_dates[0]) & (pl.col("trade_date") <= eligible_dates[-1])
        )
        if cancelled():
            raise InterruptedError("ML research was cancelled.")
        final_model = _model(selected_parameters, n_estimators=selected_rounds)
        final_model.fit(_matrix(pre_holdout), pre_holdout["relevance"].to_numpy(), group=_groups(pre_holdout))
        holdout_scores = final_model.predict(_matrix(holdout_frame))
        holdout_metrics = _extended_metrics(holdout_frame, holdout_scores)
        holdout_path = _write_predictions(training_id, "final-holdout", holdout_frame, holdout_scores, artifact_root, holdout_metrics)
        artifact_root.mkdir(parents=True, exist_ok=True)
        model_path = artifact_root / "model.txt"
        final_model.booster_.save_model(str(model_path))
        importance = sorted(
            ({"feature": feature, "gain": float(gain)} for feature, gain in zip(FEATURE_COLUMNS, final_model.booster_.feature_importance("gain"), strict=True)),
            key=lambda item: item["gain"], reverse=True,
        )
        importance_path = artifact_root / "feature-importance.json"
        importance_path.write_text(json.dumps(importance, ensure_ascii=False, indent=2), encoding="utf-8")
        mlflow.log_metrics({f"rolling_{key}": float(value) for key, value in rolling_metrics.items() if isinstance(value, (int, float)) and value is not None})
        mlflow.log_metrics({f"holdout_{key}": float(value) for key, value in holdout_metrics.items() if isinstance(value, (int, float)) and value is not None})
        model_info = mlflow.lightgbm.log_model(
            final_model, name="model", registered_model_name=MODEL_NAME,
            metadata={"deployment_status": "research_only", "training_run_id": training_id},
        )
        mlflow.log_artifact(str(importance_path), artifact_path="analysis")
        registered_version = getattr(model_info, "registered_model_version", None)
    return {
        "rollingOos": rolling_metrics, "finalHoldout": holdout_metrics,
        "featureImportance": importance, "modelPath": str(model_path),
        "selectedTrialId": str(uuid.uuid5(uuid.NAMESPACE_URL, f"ml-trial:{training_id}:0:{selected_index}")),
        "mlflowRunId": parent_run_id, "mlflowExperiment": parent_experiment_id,
        "mlflowExperimentName": experiment_name,
        "registeredModelVersion": str(registered_version) if registered_version is not None else None,
        "artifacts": {
            "rollingOosPredictions": str(oos_path), "finalHoldoutPredictions": str(holdout_path),
            "featureImportance": str(importance_path), "model": str(model_path),
        },
    }
