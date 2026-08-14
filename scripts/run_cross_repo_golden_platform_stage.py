#!/usr/bin/env python3
"""Platform-owned stages for the cross-repository Research Golden acceptance."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd


QLIB_INSTRUMENTS = ("SH600001", "SZ000001")
BENCHMARK_INSTRUMENT = "SH000300"
SOURCE = "akshare"
RESULT_MARKER = "__CROSS_REPO_GOLDEN_RESULT__="


def _configure(work_dir: Path) -> Path:
    repo = Path(__file__).resolve().parents[1]
    backend = repo / "web" / "backend"
    data_root = work_dir / "platform-data"
    runtime = work_dir / "platform-runtime"
    lake = work_dir / "platform-lake"
    for path in (data_root, runtime, lake):
        path.mkdir(parents=True, exist_ok=True)
    os.environ.update(
        {
            "LEAN_ALLOW_SQLITE_TEST_DB": "1",
            "LEAN_DATABASE_URL": f"sqlite:///{runtime / 'golden.sqlite3'}",
            "LEAN_RUNTIME_DIR": str(runtime),
            "LEAN_DATA_DIR": str(data_root),
            "LEAN_HOST_DATA_DIR": str(data_root),
            "LEAN_MARKET_DATA_DIR": str(lake),
            "LEAN_PARQUET_DIR": str(lake),
            "LEAN_HOST_PARQUET_DIR": str(lake),
            "LEAN_FILE_OBJECT_STORE_DIR": str(runtime / "stored-objects"),
            "LEAN_DB_OBJECT_STORE_ENABLED": "0",
            "LEAN_API_AUTH_REQUIRED": "0",
            "LEAN_WORKSPACE_ROOT": str(work_dir),
            "LEAN_GIT_ROOT": str(repo),
            "LEAN_HOST_PLATFORM_DIR": str(repo),
        }
    )
    sys.path.insert(0, str(backend))
    return data_root


def _market_frame() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", "2024-06-28")
    rows: list[dict[str, Any]] = []
    for instrument_index, instrument in enumerate(
        (*QLIB_INSTRUMENTS, BENCHMARK_INSTRUMENT)
    ):
        for index, trade_date in enumerate(dates):
            if instrument == "SH600001":
                close = 10.0 + 0.035 * index + 0.18 * math.sin(index / 6.0)
            elif instrument == "SZ000001":
                close = 13.0 + 0.008 * index + 0.25 * math.cos(index / 8.0)
            else:
                close = 3500.0 + 1.7 * index + 8.0 * math.sin(index / 10.0)
            open_price = close * (0.998 + instrument_index * 0.0003)
            rows.append(
                {
                    "date": trade_date.strftime("%Y-%m-%d"),
                    "symbol": instrument,
                    "open": float(open_price),
                    "high": float(max(open_price, close) * 1.008),
                    "low": float(min(open_price, close) * 0.992),
                    "close": float(close),
                    "volume": float(
                        1_000_000 + index * 1_000 + instrument_index * 20_000
                    ),
                    "money": float(close * (1_000_000 + index * 1_000)),
                    "factor": 1.0,
                    "change": 0.0,
                    "paused": 0.0,
                    "is_limit_up": 0.0,
                    "is_limit_down": 0.0,
                    "is_st": 0.0,
                    "listed_days": 1_000.0 + index,
                    "circ_mv": 50_000_000_000.0 + instrument_index * 2_000_000_000.0,
                }
            )
    return pd.DataFrame(rows)


def publish(work_dir: Path) -> dict[str, Any]:
    data_root = _configure(work_dir)
    from app import db as db_module
    from app.services.data_releases import (
        QLIB_RESEARCH_PROFILE,
        publish_data_release,
        required_components_for_profile,
    )

    db_module.init_db()
    source_root = data_root / "golden-source"
    source_root.mkdir(parents=True, exist_ok=True)
    market = _market_frame()
    coverage = {"start": str(market["date"].min()), "end": str(market["date"].max())}
    components: list[dict[str, Any]] = []
    for role in sorted(required_components_for_profile(QLIB_RESEARCH_PROFILE)):
        path = source_root / f"{role}.parquet"
        if role in {"qlib_staging", "bars", "benchmark"}:
            frame = (
                market
                if role != "benchmark"
                else market.loc[market["symbol"].eq(BENCHMARK_INSTRUMENT)].copy()
            )
        elif role == "pit_universe":
            frame = pd.DataFrame(
                [
                    {
                        "instrument": instrument,
                        "effective_from": coverage["start"],
                        "effective_to": coverage["end"],
                    }
                    for instrument in QLIB_INSTRUMENTS
                ]
            )
        elif role == "industry_classification_pit":
            frame = pd.DataFrame(
                [
                    {
                        "instrument": instrument,
                        "effective_from": coverage["start"],
                        "effective_to": coverage["end"],
                        "industry_code": str(801010 + index * 10),
                        "industry_name": f"Golden Industry {index + 1}",
                        "taxonomy": "SW2021",
                        "level_no": 1,
                    }
                    for index, instrument in enumerate(QLIB_INSTRUMENTS)
                ]
            )
        elif role == "security_master":
            frame = pd.DataFrame(
                [
                    {
                        "instrument": instrument,
                        "listed_date": "2000-01-01",
                        "delisted_date": None,
                    }
                    for instrument in QLIB_INSTRUMENTS
                ]
            )
        elif role == "trading_calendar":
            frame = pd.DataFrame(
                {"date": sorted(market["date"].unique()), "is_open": True}
            )
        else:
            frame = pd.DataFrame([{"role": role, "as_of_date": coverage["end"]}])
        frame.to_parquet(path, index=False)
        components.append(
            {
                "role": role,
                "componentReleaseId": f"golden:{role}:v1",
                "datasetKey": role,
                "schemaVersion": "1.0",
                "coverage": coverage,
                "files": [{"path": str(path), "rowCount": len(frame)}],
            }
        )
    release = publish_data_release(
        {
            "profile": QLIB_RESEARCH_PROFILE,
            "assetClass": "equity",
            "market": "china",
            "universe": "CSI300_GOLDEN",
            "benchmark": BENCHMARK_INSTRUMENT,
            "coverage": coverage,
            "asOfTime": f"{coverage['end']}T23:59:59+08:00",
            "components": components,
            "policies": {"pit": "effective_interval", "price": "raw"},
            "lineage": {"source": "deterministic_cross_repo_golden_v1"},
        },
        data_root,
    )
    return {
        "dataReleaseId": release["dataReleaseId"],
        "dataRoot": str(data_root),
        "manifest": str(
            data_root / "releases" / release["dataReleaseId"] / "manifest.json"
        ),
    }


def _release_market(data_root: Path, release_id: str) -> pd.DataFrame:
    manifest_path = data_root / "releases" / release_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    component = next(
        item for item in manifest["components"] if item["role"] == "qlib_staging"
    )
    return pd.concat(
        (
            pd.read_parquet(manifest_path.parent / item["path"])
            for item in component["files"]
        ),
        ignore_index=True,
    )


def _platform_rows(market: pd.DataFrame, instrument: str) -> list[dict[str, Any]]:
    selected = market.loc[market["symbol"].eq(instrument)].sort_values("date")
    return [
        {
            "date": str(row.date),
            "open": float(row.open),
            "high": float(row.high),
            "low": float(row.low),
            "close": float(row.close),
            "volume": float(row.volume),
            "adj_factor": 1.0,
            "canBuy": True,
            "canSell": True,
        }
        for row in selected.itertuples(index=False)
    ]


def _import_bars(market: pd.DataFrame, selected: str) -> None:
    from app.services.data import import_ashare_research_data

    for instrument in (selected, BENCHMARK_INSTRUMENT):
        import_ashare_research_data(
            symbol=instrument[2:],
            provider=SOURCE,
            market="china",
            rows=_platform_rows(market, instrument),
            source=SOURCE,
            overwrite=True,
            adjust="raw",
            outputsize="",
            asset_class="equity",
            venue="china",
            resolution="daily",
            data_type="trade",
            start_date=None,
            end_date=None,
        )


def _install_results_analyzer_reference() -> None:
    from app.lean_engine.data_writers import write_lean_daily_zip

    rows = []
    for index, trade_date in enumerate(pd.bdate_range("1993-01-29", "2024-06-28")):
        close = 40.0 + index * 0.02
        rows.append(
            {
                "date": trade_date.strftime("%Y-%m-%d"),
                "open": str(close),
                "high": str(close * 1.002),
                "low": str(close * 0.998),
                "close": str(close),
                "volume": "1000000",
            }
        )
    write_lean_daily_zip("SPY", rows, "golden-reference", overwrite=True, market="usa")


def _write_target_algorithm(project: dict[str, Any]) -> None:
    from app.services.projects import write_file

    write_file(
        str(project["id"]),
        str(project["main_file"]),
        """from AlgorithmImports import *
from ashare_execution import AShareExecutionHelper, apply_ashare_models


class GoldenTargetAlgorithm(QCAlgorithm):
    def initialize(self):
        Market.Add("china", 101)
        self.set_start_date(*map(int, self.get_parameter("start").split("-")))
        self.set_end_date(*map(int, self.get_parameter("end").split("-")))
        self.set_account_currency("CNY")
        self.set_cash(float(self.get_parameter("initialCash")))
        self.set_brokerage_model(BrokerageName.DEFAULT, AccountType.CASH)
        self.debug("AShare execution account type: cash; short selling disabled.")
        equity = self.add_equity(
            self.get_parameter("ticker"), Resolution.DAILY, "china",
            data_normalization_mode=DataNormalizationMode.RAW,
        )
        self.symbol = equity.symbol
        self.signal_date = self.get_parameter("qlibSignalDate")
        self.target_weight = float(self.get_parameter("qlibTargetWeight"))
        self.set_benchmark(lambda time: 1)
        apply_ashare_models(self, equity)
        self.helper = AShareExecutionHelper(
            self, self.get_parameter("ashareStatusFile", "/Lean/Run/ashare_trade_status.json")
        )
        self.submitted = False

    def on_data(self, data):
        if self.submitted or self.time.strftime("%Y-%m-%d") != self.signal_date:
            return
        if not data.contains_key(self.symbol):
            return
        self.helper.target_percent(self.symbol, self.target_weight)
        self.submitted = True

    def on_order_event(self, order_event):
        self.helper.on_order_event(order_event)
""",
    )


def _run_lean(
    *,
    selected: str,
    signal_date: str,
    target_weight: float,
    release_id: str,
    research_run_id: str,
    target_artifact_id: str,
    targets_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    from app.repositories.backtest_repository import get_backtest
    from app.services.backtest_service import create_backtest_job
    from app.services.projects import create_project
    from app.services.qlib_promotion import record_lean_validation
    from app.tasks.worker import run_backtest_task

    project = create_project(
        "Cross Repo Golden Target",
        algorithm_class="GoldenTargetAlgorithm",
        market="china",
    )
    _write_target_algorithm(project)
    job = create_backtest_job(
        {
            "symbol": selected[2:],
            "assetClass": "equity",
            "market": "china",
            "venue": "china",
            "resolution": "daily",
            "dataType": "trade",
            "start": "2024-01-02",
            "end": "2024-06-28",
            "cash": 1_000_000,
            "projectId": project["id"],
            "source": SOURCE,
            "allowResearchSource": True,
            "extra": {
                "source": SOURCE,
                "allowResearchSource": True,
                "allowTruncatedData": True,
                "benchmarkSymbol": BENCHMARK_INSTRUMENT[2:],
                "dataReleaseId": release_id,
                "qlibTargetPortfolioArtifactId": target_artifact_id,
                "qlibTargetsSha256": targets_sha256,
                "qlibSignalDate": signal_date,
                "qlibTargetWeight": target_weight,
                "sourceResearchRunId": research_run_id,
            },
        }
    )
    task_result = run_backtest_task.run(job["task_id"], job["id"])
    backtest = get_backtest(str(job["id"]))
    if (
        not backtest
        or task_result.get("status") != "success"
        or backtest.get("status") != "success"
    ):
        raise RuntimeError(
            f"Real LEAN golden backtest failed: {backtest or task_result}"
        )
    validation = record_lean_validation(
        research_run_id, lean_backtest_run_id=str(job["id"])
    )
    if validation.get("status") != "LEAN_VALIDATED":
        raise AssertionError(f"Unexpected promotion status: {validation}")
    return backtest, validation


def validate(work_dir: Path, bundle_path: Path) -> dict[str, Any]:
    data_root = _configure(work_dir)
    from app import db as db_module
    from app.services import object_store, qlib_import_v2

    db_module.init_db()
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    uploads = json.loads(
        bundle_path.with_name("qlib_research_bundle.v2.uploads.json").read_text(
            encoding="utf-8"
        )
    )["uploads"]
    for object_key, local_path in uploads.items():
        object_store.put_item(str(object_key), Path(str(local_path)).read_bytes())
    imported = qlib_import_v2.import_run(bundle)
    research_run_id = str(imported["researchRunId"])
    target = next(
        item
        for item in bundle["artifacts"]
        if item["artifactType"] == "TARGET_PORTFOLIO"
    )
    target_payload = json.loads(
        Path(uploads[target["payloadRef"]["objectKey"]]).read_text()
    )
    selected_target = target_payload["targets"][0]
    selected = str(selected_target["instrument"])
    target_id = str(target["artifactId"])
    targets_sha = str(target["metadata"]["targetsSha256"])
    release_id = str(target["dataReleaseId"])
    market = _release_market(data_root, release_id)
    _import_bars(market, selected)
    _install_results_analyzer_reference()
    backtest, lean_validation = _run_lean(
        selected=selected,
        signal_date=str(target["signalDate"]),
        target_weight=float(selected_target["targetWeight"]),
        release_id=release_id,
        research_run_id=research_run_id,
        target_artifact_id=target_id,
        targets_sha256=targets_sha,
    )
    with db_module.db() as connection:
        row = connection.execute(
            "select * from artifact_registry where artifact_id=?", (target_id,)
        ).fetchone()
        stored_target = dict(row) if row else None
    if not stored_target or stored_target["promotion_status"] != "LEAN_VALIDATED":
        raise AssertionError("TargetPortfolio was not promoted by platform")
    return {
        "dataReleaseId": release_id,
        "targetPortfolioArtifactId": target_id,
        "targetsSha256": targets_sha,
        "researchRunId": research_run_id,
        "leanBacktestRunId": backtest["id"],
        "leanDataReleaseId": backtest["data_release_id"],
        "leanTargetPortfolioArtifactId": backtest["parameters"][
            "qlibTargetPortfolioArtifactId"
        ],
        "leanTargetsSha256": backtest["parameters"]["qlibTargetsSha256"],
        "executionValidationPassed": bool(backtest["validation"]["passed"]),
        "promotionStatus": stored_target["promotion_status"],
        "validationArtifactId": lean_validation["validationArtifactId"],
        "selectedInstrument": selected,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("publish", "validate"))
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--bundle", type=Path)
    args = parser.parse_args()
    work_dir = args.work_dir.expanduser().resolve()
    if args.stage == "publish":
        result = publish(work_dir)
    else:
        if args.bundle is None:
            parser.error("validate requires --bundle")
        result = validate(work_dir, args.bundle.expanduser().resolve())
    print(RESULT_MARKER + json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
