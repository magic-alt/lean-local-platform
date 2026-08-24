from __future__ import annotations

import hashlib
import json
import os
import statistics
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

import polars as pl

from ..core.config import PARQUET_COMPRESSION, PARQUET_DIR
from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now
from ..ml.cross_sectional import (
    FEATURE_COLUMNS,
    FEATURE_VERSION,
    add_forward_labels,
    add_valuation_features,
    assess_quality,
    build_price_features,
    build_walk_forward_plan,
    candidate_grid,
    prediction_metrics,
    preprocess_cross_section,
)
from . import db_object_store, ml_data_preparation, market_lake


TEMPLATE_KEY = "ml-cross-sectional-ranker"
MODEL_NAME = "lean-ashare-csi300-lgbm-ranker"
FINANCIAL_FIELDS = (
    "roe", "grossprofit_margin", "netprofit_yoy", "or_yoy", "debt_to_assets",
    "n_cashflow_act", "n_income",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def default_parameters(parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    values = dict(parameters or {})
    return {
        "universeCode": "CSI300",
        "benchmarkCode": "000300",
        "startDate": str(values.get("startDate") or "2015-01-01")[:10],
        "endDate": str(values.get("endDate") or date.today().isoformat())[:10],
        "horizonTradingDays": 5,
        "minimumGroupSize": 150,
        "minimumListedTradingDays": 250,
        "featureVersion": FEATURE_VERSION,
        "candidateGrid": candidate_grid(),
        "finalHoldoutMonths": 12,
    }


def validate_scope(scope: dict[str, Any], parameters: dict[str, Any] | None = None) -> None:
    selection = scope.get("selection") or {}
    asset = scope.get("asset") or {}
    price = scope.get("price") or {}
    provider = scope.get("provider") or {}
    time_scope = scope.get("time") or {}
    config = default_parameters(parameters)
    values = [str(value).upper() for value in selection.get("values") or []]
    if selection.get("type") != "universe" or values != ["CSI300"]:
        raise ValueError("ML research requires selection.type=universe and values=[CSI300].")
    if asset.get("market") != "china" or asset.get("resolution") != "daily":
        raise ValueError("ML research requires China daily equity data.")
    if price.get("adjust") != "raw":
        raise ValueError("ML research requires raw execution prices; adjustment factors are applied inside features and labels.")
    if provider.get("source") != "tushare" or provider.get("mode") != "strict" or provider.get("allowResearchSource"):
        raise ValueError("ML research requires strict TuShare canonical data without research-source fallback.")
    for scope_key, config_key in (("startDate", "startDate"), ("endDate", "endDate")):
        scoped = time_scope.get(scope_key)
        if scoped and str(scoped)[:10] != config[config_key]:
            raise ValueError(f"ML parameter {config_key} must match scope.time.{scope_key}.")


def preview(parameters: dict[str, Any] | None = None, *, scope: dict[str, Any] | None = None) -> dict[str, Any]:
    config = default_parameters(parameters)
    if scope is not None:
        validate_scope(scope, parameters)
    preparation = ml_data_preparation.preparation_preview(config["startDate"], config["endDate"])
    folds = None
    fold_error = None
    try:
        with db() as connection:
            rows = connection.execute(
                "select trade_date from trade_calendar where market='china' and is_open=1 and trade_date between ? and ? order by trade_date",
                (config["startDate"], config["endDate"]),
            ).fetchall()
        folds = build_walk_forward_plan([row["trade_date"] for row in rows])
    except Exception as exc:
        fold_error = str(exc)
    blocking = list(preparation["blocking"])
    if fold_error:
        blocking.append("insufficient_walk_forward_history")
    return {
        "template": TEMPLATE_KEY, "ready": not blocking, "blocking": blocking,
        "coverage": preparation["coverage"], "historicalMemberSymbols": preparation["historicalMemberSymbols"],
        "preparationRequest": preparation["preparationRequest"], "foldPlan": folds,
        "foldPlanError": fold_error, "candidateCount": len(config["candidateGrid"]),
        "finalHoldoutMonths": 12, "qualityThresholds": {
            "meanRankIc": 0.02, "annualizedIcir": 0.5, "q5MinusQ1": 0.0,
        }, "parameters": config,
    }


def create_training_record(research_run_id: str, parameters: dict[str, Any]) -> dict[str, Any]:
    item_id = str(uuid.uuid4())
    now = utc_now()
    with db() as connection:
        connection.execute(
            """
            insert into ml_training_runs
                (id,research_run_id,status,stage,progress,metrics_json,quality_json,
                 fold_plan_json,artifacts_json,created_at,updated_at)
            values (?,?,'queued','queued',0,'{}','{}','{}','{}',?,?)
            """,
            (item_id, research_run_id, now, now),
        )
    return training_detail(item_id)


def training_for_research(research_run_id: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute("select * from ml_training_runs where research_run_id=?", (research_run_id,)).fetchone()
    return row_to_dict(row)


def training_detail(training_id: str) -> dict[str, Any]:
    with db() as connection:
        row = connection.execute("select * from ml_training_runs where id=?", (training_id,)).fetchone()
        trials = connection.execute(
            "select * from ml_training_trials where training_run_id=? order by fold_index,candidate_index", (training_id,)
        ).fetchall()
        files = connection.execute(
            "select * from ml_prediction_files where training_run_id=? order by split_key", (training_id,)
        ).fetchall()
    item = row_to_dict(row)
    if not item:
        raise KeyError("ML training run not found.")
    item["trials"] = rows_to_dicts(trials)
    item["predictionFiles"] = rows_to_dicts(files)
    tracking_uri = os.environ.get("MLFLOW_PUBLIC_URL") or os.environ.get("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000")
    tracking_uri = tracking_uri.rstrip("/")
    if item.get("mlflow_run_id"):
        item["mlflowUrl"] = f"{tracking_uri}/#/experiments/{item.get('mlflow_experiment') or '0'}/runs/{item['mlflow_run_id']}"
    return item


def _update(training_id: str, *, stage: str, progress: float, status: str = "running", **values: Any) -> None:
    columns = ["status=?", "stage=?", "progress=?", "updated_at=?"]
    parameters: list[Any] = [status, stage, max(0.0, min(1.0, progress)), utc_now()]
    json_fields = {"metrics", "quality", "fold_plan", "artifacts"}
    for key, value in values.items():
        column = f"{key}_json" if key in json_fields else key
        columns.append(f"{column}=?")
        parameters.append(json_dump(value) if key in json_fields else value)
    parameters.append(training_id)
    with db() as connection:
        connection.execute(f"update ml_training_runs set {', '.join(columns)} where id=?", parameters)


def _stream_frame(sql: str, parameters: tuple[Any, ...]) -> pl.DataFrame:
    batches: list[pl.DataFrame] = []
    with db() as connection:
        if hasattr(connection, "iter_batches"):
            for rows in connection.iter_batches(sql, parameters, batch_size=100_000):
                if rows:
                    batches.append(pl.DataFrame(rows, infer_schema_length=None))
        else:
            rows = connection.execute(sql, parameters).fetchall()
            if rows:
                batches.append(pl.DataFrame([dict(row) for row in rows], infer_schema_length=None))
    return pl.concat(batches, how="vertical_relaxed") if batches else pl.DataFrame()


def _load_panel(start_date: str, end_date: str) -> tuple[pl.DataFrame, pl.DataFrame, dict[str, Any]]:
    load_start = f"{max(1990, int(start_date[:4]) - 2):04d}-01-01"
    memberships = _stream_frame(
        """select symbol,start_date,end_date,announce_date,effective_date from universe_membership
           where universe_code='CSI300' and start_date<=? and coalesce(end_date,?)>=?""",
        (end_date, end_date, load_start),
    )
    symbols = sorted(memberships["symbol"].unique().to_list()) if not memberships.is_empty() else []
    if not symbols:
        raise ValueError("No PIT CSI300 membership is available for the requested range.")
    placeholders = ",".join("?" for _ in symbols)
    predicates = (f"symbol in ({placeholders})", "trade_date between ? and ?")
    parameters = [*symbols, load_start, end_date]
    bar_rows = market_lake.query_rows(
        kind="bars", asset_class="equity", market="china", venue="china", resolution="daily",
        data_type="trade", adjust="raw", source="tushare",
        columns="symbol,trade_date,open,high,low,close,volume,amount,adj_factor",
        predicates=predicates, parameters=parameters, order_by="symbol,trade_date",
    )
    bars = pl.DataFrame(bar_rows, infer_schema_length=None) if bar_rows else pl.DataFrame()
    if bars.is_empty():
        raise ValueError("No PIT CSI300 daily bars are available for the requested range.")
    adjustments = market_lake.query_rows(
        kind="adjustment_factor", asset_class="equity", market="china", venue="china",
        resolution="daily", data_type="factor", source="tushare", columns="symbol,trade_date,adj_factor",
        predicates=predicates, parameters=parameters,
    )
    if adjustments:
        bars = bars.drop("adj_factor").join(pl.DataFrame(adjustments), on=["symbol", "trade_date"], how="left")
    bars = bars.with_columns(pl.col("adj_factor").fill_null(1.0))
    securities = _stream_frame(
        f"select symbol,listed_date from securities where symbol in ({placeholders})", tuple(symbols)
    )
    bars = bars.join(securities, on="symbol", how="left") if not securities.is_empty() else bars.with_columns(pl.lit(None).alias("listed_date"))
    statuses = market_lake.query_matching(
        kind="trade_status", asset_class="equity", market="china", venue="china", resolution="daily",
        data_type="status", columns="symbol,trade_date,is_suspended,is_st",
        predicates=predicates, parameters=parameters,
    )
    if statuses:
        status_frame = pl.DataFrame(statuses).group_by(["symbol", "trade_date"]).agg(
            pl.col("is_suspended").max(), pl.col("is_st").max()
        )
        bars = bars.join(status_frame, on=["symbol", "trade_date"], how="left")
    else:
        bars = bars.with_columns(pl.lit(0).alias("is_suspended"), pl.lit(0).alias("is_st"))
    intervals: dict[str, list[tuple[str, str]]] = {}
    for row in memberships.to_dicts():
        intervals.setdefault(str(row["symbol"]), []).append((str(row["start_date"])[:10], str(row.get("end_date") or end_date)[:10]))
    industry_rows = _stream_frame(
        f"""select symbol,industry_code,in_date,out_date from industry_membership
            where taxonomy='SW2021' and level_no=1 and symbol in ({placeholders}) and in_date<=?""",
        (*symbols, end_date),
    )
    industries: dict[str, list[tuple[str, str, str]]] = {}
    for row in industry_rows.to_dicts() if not industry_rows.is_empty() else []:
        industries.setdefault(str(row["symbol"]), []).append(
            (str(row["in_date"])[:10], str(row.get("out_date") or end_date)[:10], str(row["industry_code"]))
        )
    bars = bars.with_columns(
        pl.struct("symbol", "trade_date").map_elements(
            lambda item: int(any(start <= str(item["trade_date"]) <= end for start, end in intervals.get(str(item["symbol"]), []))),
            return_dtype=pl.Int8,
        ).alias("is_member"),
        pl.struct("symbol", "trade_date").map_elements(
            lambda item: next((code for start, end, code in reversed(industries.get(str(item["symbol"]), []))
                               if start <= str(item["trade_date"]) <= end), None),
            return_dtype=pl.String,
        ).alias("industry_code"),
        pl.col("is_suspended").fill_null(0), pl.col("is_st").fill_null(0),
    )
    valuation_rows = market_lake.query_rows(
        kind="daily_basic", asset_class="equity", market="china", venue="china", resolution="daily",
        data_type="metric", source="tushare:daily_basic",
        columns="symbol,trade_date,turnover_rate,volume_ratio,pe_ttm,pb,ps_ttm,total_mv_cny total_mv",
        predicates=predicates, parameters=parameters,
    )
    valuation = pl.DataFrame(valuation_rows, infer_schema_length=None) if valuation_rows else pl.DataFrame()
    if not valuation.is_empty():
        bars = bars.join(valuation, on=["symbol", "trade_date"], how="left")
    else:
        bars = bars.with_columns(*(pl.lit(None).cast(pl.Float64).alias(name) for name in ("turnover_rate", "volume_ratio", "pe_ttm", "pb", "ps_ttm", "total_mv")))
    facts = _stream_frame(
        f"""
        select symbol,field_name,report_date,effective_date,value from financial_facts
        where effective_date<=? and report_date>=? and field_name in ({','.join('?' for _ in FINANCIAL_FIELDS)})
        order by symbol,effective_date,report_date
        """,
        (end_date, load_start, *FINANCIAL_FIELDS),
    )
    if not facts.is_empty():
        cash = facts.filter(pl.col("field_name") == "n_cashflow_act").select(
            "symbol", "report_date", pl.col("effective_date").alias("cash_effective"), pl.col("value").alias("n_cashflow_act")
        ).unique(["symbol", "report_date"], keep="last")
        income = facts.filter(pl.col("field_name") == "n_income").select(
            "symbol", "report_date", pl.col("effective_date").alias("income_effective"), pl.col("value").alias("n_income")
        ).unique(["symbol", "report_date"], keep="last")
        ratio = cash.join(income, on=["symbol", "report_date"], how="inner").with_columns(
            pl.max_horizontal("cash_effective", "income_effective").alias("effective_date"),
            pl.when(pl.col("n_income").abs() > 1e-12).then(pl.col("n_cashflow_act") / pl.col("n_income")).otherwise(None).alias("operating_cashflow_to_profit"),
        ).sort(["symbol", "effective_date", "report_date"]).unique(["symbol", "effective_date"], keep="last")
        metric_facts = facts.filter(~pl.col("field_name").is_in(["n_cashflow_act", "n_income"]))
        pivot = metric_facts.pivot(on="field_name", index=["symbol", "effective_date", "report_date"], values="value", aggregate_function="last")
        pivot = pivot.sort(["symbol", "effective_date", "report_date"]).unique(["symbol", "effective_date"], keep="last")
        finance_columns = [name for name in FEATURE_COLUMNS if name in pivot.columns]
        bars = bars.sort(["symbol", "trade_date"]).join_asof(
            pivot.select("symbol", "effective_date", *finance_columns).sort(["symbol", "effective_date"]),
            left_on="trade_date", right_on="effective_date", by="symbol", strategy="backward",
        ).drop("effective_date")
        if not ratio.is_empty():
            bars = bars.sort(["symbol", "trade_date"]).join_asof(
                ratio.select("symbol", "effective_date", "operating_cashflow_to_profit").sort(["symbol", "effective_date"]),
                left_on="trade_date", right_on="effective_date", by="symbol", strategy="backward",
            ).drop("effective_date")
    for name in ("roe", "grossprofit_margin", "netprofit_yoy", "or_yoy", "debt_to_assets", "operating_cashflow_to_profit"):
        if name not in bars.columns:
            bars = bars.with_columns(pl.lit(None).cast(pl.Float64).alias(name))
    benchmark_rows = market_lake.query_rows(
        kind="bars", asset_class="index", market="china", venue="china", resolution="daily",
        data_type="trade", adjust="raw", source="tushare",
        columns="trade_date,open,close,coalesce(adj_factor,1.0) adj_factor",
        predicates=("symbol='000300'", "trade_date between ? and ?"), parameters=(load_start, end_date),
        order_by="trade_date",
    )
    benchmark = pl.DataFrame(benchmark_rows, infer_schema_length=None) if benchmark_rows else pl.DataFrame()
    if benchmark.is_empty():
        raise ValueError("CSI300 benchmark bars are missing.")
    manifest = {
        "loadStart": load_start, "sampleStart": start_date, "endDate": end_date,
        "barRows": bars.height, "symbols": bars["symbol"].n_unique(),
        "benchmarkRows": benchmark.height, "valuationRows": valuation.height,
        "financialFactRows": facts.height,
    }
    return bars, benchmark, manifest


def _coverage(panel: pl.DataFrame, start_date: str) -> dict[str, Any]:
    sample = panel.filter(pl.col("trade_date") >= start_date)
    total = max(1, sample.height)
    ratios = {name: sample[name].is_not_null().sum() / total for name in FEATURE_COLUMNS if name in sample.columns}
    result = {
        "rows": sample.height, "symbols": sample["symbol"].n_unique(),
        "industry": sample["industry_code"].is_not_null().sum() / total,
        "valuationMinimum": min((ratios.get(name, 0.0) for name in ("turnover_rate", "volume_ratio", "earnings_yield_ttm", "book_to_price", "sales_to_price_ttm", "log_total_mv")), default=0.0),
        "financialMinimum": min((ratios.get(name, 0.0) for name in ("roe", "grossprofit_margin", "netprofit_yoy", "or_yoy", "debt_to_assets", "operating_cashflow_to_profit")), default=0.0),
        "featureCoverage": ratios,
    }
    result["blocking"] = []
    if result["industry"] < 0.95:
        result["blocking"].append("industry_coverage_below_95pct")
    if result["valuationMinimum"] < 0.95:
        result["blocking"].append("daily_basic_coverage_below_95pct")
    if result["financialMinimum"] < 0.70:
        result["blocking"].append("financial_coverage_below_70pct")
    return result


def materialize_feature_set(training_id: str, config: dict[str, Any], log: Callable[[str], None]) -> tuple[str, Path, dict[str, Any]]:
    log("Loading PIT CSI300 panel from the canonical PostgreSQL control plane.")
    panel, benchmark, source_manifest = _load_panel(config["startDate"], config["endDate"])
    log("Calculating causal price, valuation, financial and five-day excess-return labels.")
    panel = add_valuation_features(build_price_features(panel))
    panel = panel.with_columns(pl.col("trade_date").cum_count().over("symbol").alias("listed_trading_days"))
    panel = add_forward_labels(panel, benchmark, eligibility_column="is_member")
    panel = panel.filter(
        (pl.col("trade_date") >= config["startDate"]) &
        (pl.col("is_member") == 1) &
        (pl.col("listed_trading_days") >= 250) &
        (pl.col("is_suspended") == 0) & (pl.col("is_st") == 0)
    )
    coverage = _coverage(panel, config["startDate"])
    if coverage["blocking"]:
        raise ValueError("; ".join(coverage["blocking"]))
    panel = preprocess_cross_section(panel).select(
        "trade_date", "symbol", "industry_code", "label_return", "relevance", *FEATURE_COLUMNS,
    ).filter(pl.col("relevance").is_not_null())
    small_dates = panel.group_by("trade_date").len().filter(pl.col("len") < 150).height
    date_count = panel["trade_date"].n_unique()
    if date_count and small_dates / date_count > 0.01:
        raise ValueError("More than 1% of sample dates contain fewer than 150 eligible stocks.")
    fold_plan = build_walk_forward_plan(panel["trade_date"].unique().to_list())
    manifest = {
        "featureVersion": FEATURE_VERSION, "features": list(FEATURE_COLUMNS),
        "source": source_manifest, "coverage": coverage, "foldPlan": fold_plan,
        "rows": panel.height, "symbols": panel["symbol"].n_unique(),
    }
    staging_directory = PARQUET_DIR / "ml" / "feature-sets" / ".staging" / training_id
    staging_directory.mkdir(parents=True, exist_ok=True)
    staging_path = staging_directory / "panel.parquet"
    panel.write_parquet(staging_path, compression=PARQUET_COMPRESSION)
    manifest["panelSha256"] = _sha256(staging_path)
    fingerprint = _fingerprint(manifest)
    manifest["fingerprint"] = fingerprint
    directory = PARQUET_DIR / "ml" / "feature-sets" / fingerprint
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "panel.parquet"
    if not path.exists() or _sha256(path) != manifest["panelSha256"]:
        staging_path.replace(path)
    elif staging_path.exists():
        staging_path.unlink()
    try:
        staging_directory.rmdir()
        staging_directory.parent.rmdir()
    except OSError:
        pass
    now = utc_now()
    feature_set_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"ml-feature-set:{fingerprint}"))
    file_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"ml-feature-file:{fingerprint}:panel.parquet"))
    with db() as connection:
        connection.execute(
            """insert into ml_feature_sets
               (id,fingerprint,universe_code,start_date,end_date,feature_version,status,row_count,
                symbol_count,feature_count,manifest_json,coverage_json,created_at,completed_at)
               values (?,?,?,?,?,?,'ready',?,?,?,?,?,?,?,?)
               on conflict(fingerprint) do update set status='ready',row_count=excluded.row_count,
                 symbol_count=excluded.symbol_count,manifest_json=excluded.manifest_json,
                 coverage_json=excluded.coverage_json,completed_at=excluded.completed_at""",
            (feature_set_id, fingerprint, "CSI300", config["startDate"], config["endDate"], FEATURE_VERSION,
             panel.height, panel["symbol"].n_unique(), len(FEATURE_COLUMNS), json_dump(manifest), json_dump(coverage), now, now),
        )
        connection.execute(
            """insert into ml_feature_files
               (id,feature_set_id,relative_path,sha256,row_count,min_date,max_date,size_bytes,created_at)
               values (?,?,?,?,?,?,?,?,?)
               on conflict(feature_set_id,relative_path) do update set sha256=excluded.sha256,
                 row_count=excluded.row_count,size_bytes=excluded.size_bytes""",
            (file_id, feature_set_id, str(path.relative_to(PARQUET_DIR)), _sha256(path), panel.height,
             panel["trade_date"].min(), panel["trade_date"].max(), path.stat().st_size, now),
        )
    _update(training_id, stage="training", progress=0.25, feature_set_id=feature_set_id, fold_plan=fold_plan)
    return feature_set_id, path, manifest


def run_training(research_run_id: str, *, log: Callable[[str], None], cancelled: Callable[[], bool]) -> dict[str, Any]:
    training = training_for_research(research_run_id)
    if not training:
        raise KeyError("ML training metadata is missing.")
    training_id = str(training["id"])
    with db() as connection:
        research = connection.execute("select * from research_runs where id=?", (research_run_id,)).fetchone()
    if not research:
        raise KeyError("Research run not found.")
    research = row_to_dict(research) or {}
    config = default_parameters(research.get("parameters") or {})
    now = utc_now()
    _update(training_id, stage="feature_build", progress=0.02, started_at=now)
    try:
        feature_set_id, path, manifest = materialize_feature_set(training_id, config, log)
        if cancelled():
            raise InterruptedError("ML research was cancelled.")
        from ..ml.training import train_ranker

        result = train_ranker(
            training_id=training_id, feature_path=path, fold_plan=manifest["foldPlan"],
            artifact_root=PARQUET_DIR / "ml" / "training-runs" / training_id,
            log=log, cancelled=cancelled,
        )
        quality = assess_quality(result["rollingOos"], result["finalHoldout"])
        artifacts = dict(result["artifacts"])
        if result.get("modelPath"):
            stored = db_object_store.put_file(
                "ml-models", f"{MODEL_NAME}/{training_id}/model.txt", result["modelPath"],
                metadata={"researchRunId": research_run_id, "featureSetId": feature_set_id, "metrics": result["finalHoldout"]},
            )
            artifacts["storedObjectId"] = stored.get("id")
            artifacts["modelSha256"] = _sha256(Path(result["modelPath"]))
        _update(
            training_id, stage="completed", progress=1.0, status="success",
            metrics={"rollingOos": result["rollingOos"], "finalHoldout": result["finalHoldout"], "featureImportance": result["featureImportance"]},
            quality=quality, artifacts=artifacts, mlflow_run_id=result.get("mlflowRunId"),
            mlflow_experiment=result.get("mlflowExperiment"), registered_model_name=MODEL_NAME,
            registered_model_version=result.get("registeredModelVersion"), selected_trial_id=result.get("selectedTrialId"),
            finished_at=utc_now(),
        )
        summary = {
            "technicalSuccess": True, "qualified": quality["qualified"],
            "rollingOos": result["rollingOos"], "finalHoldout": result["finalHoldout"],
            "featureSetFingerprint": manifest["fingerprint"], "modelVersion": result.get("registeredModelVersion"),
        }
        research_result = {
            "schemaVersion": "1.0", "template": TEMPLATE_KEY,
            "dataFingerprint": manifest["fingerprint"], "summary": summary, "charts": [],
            "tables": [
                {"name": "rollingOosMetrics", "columns": ["metric", "value"], "rows": [
                    {"metric": key, "value": value} for key, value in result["rollingOos"].items()
                ]},
                {"name": "finalHoldoutMetrics", "columns": ["metric", "value"], "rows": [
                    {"metric": key, "value": value} for key, value in result["finalHoldout"].items()
                ]},
                {"name": "featureImportance", "columns": ["feature", "gain"], "rows": result["featureImportance"]},
                {"name": "qualityChecks", "columns": ["split", "metric", "value", "threshold", "passed"], "rows": quality["checks"]},
            ], "warnings": [] if quality["qualified"] else ["Model completed but did not meet advisory research thresholds."],
        }
        with db() as connection:
            connection.execute(
                "update research_runs set status='success',result_json=?,summary_json=?,data_fingerprint=?,finished_at=? where id=?",
                (json_dump(research_result), json_dump(summary), manifest["fingerprint"], utc_now(), research_run_id),
            )
            connection.execute("update research_run_items set status='success',result_json=?,finished_at=? where run_id=?", (json_dump(research_result), utc_now(), research_run_id))
        return training_detail(training_id)
    except InterruptedError as exc:
        current = training_for_research(research_run_id) or training
        _update(training_id, stage="cancelled", progress=float(current.get("progress") or 0), status="cancelled", error=str(exc), finished_at=utc_now())
        with db() as connection:
            connection.execute("update research_runs set status='cancelled',error=?,finished_at=? where id=?", (str(exc), utc_now(), research_run_id))
        return training_detail(training_id)
    except Exception as exc:
        current = training_for_research(research_run_id) or training
        _update(training_id, stage="failed", progress=float(current.get("progress") or 0), status="failed", error=str(exc), finished_at=utc_now())
        with db() as connection:
            connection.execute("update research_runs set status='failed',error=?,finished_at=? where id=?", (str(exc), utc_now(), research_run_id))
            connection.execute("update research_run_items set status='failed',error=?,finished_at=? where run_id=?", (str(exc), utc_now(), research_run_id))
        raise


def artifact_path(research_run_id: str, artifact_key: str) -> Path:
    training = training_for_research(research_run_id)
    if not training:
        raise KeyError("ML training run not found.")
    artifacts = training.get("artifacts") or {}
    raw = artifacts.get(artifact_key)
    if not raw:
        raise KeyError("ML artifact not found.")
    path = Path(str(raw)).resolve()
    allowed = (PARQUET_DIR / "ml").resolve()
    if path != allowed and allowed not in path.parents:
        raise ValueError("ML artifact path is outside the managed artifact root.")
    return path
