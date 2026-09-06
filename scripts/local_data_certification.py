#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"


def _sql_path(path: Path | str) -> str:
    return str(path).replace("\\", "/").replace("'", "''")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_sha() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _query_one(connection: Any, sql: str, parameters: list[Any] | None = None) -> dict[str, Any]:
    cursor = connection.execute(sql, parameters or [])
    names = [item[0] for item in cursor.description]
    row = cursor.fetchone()
    return dict(zip(names, row, strict=True)) if row else {}


def _inventory(data_dir: Path, *, deep: bool) -> dict[str, Any]:
    try:
        import duckdb
        import polars as pl
    except Exception as exc:
        return {"passed": False, "error": f"duckdb/polars unavailable: {exc}"}

    equity_root = data_dir / "silver" / "daily" / "current"
    daily_basic_root = data_dir / "bronze" / "tushare" / "current" / "daily_basic"
    index_path = data_dir / "gold" / "qlib_staging" / "full" / "SH000300.parquet"
    equity_pattern = equity_root / "trade_date=*" / "data.parquet"
    daily_basic_pattern = daily_basic_root / "trade_date=*" / "data.parquet"

    layouts = {
        "equity": {
            "path": str(equity_root),
            "files": len(list(equity_root.glob("trade_date=*/data.parquet"))) if equity_root.is_dir() else 0,
        },
        "dailyBasic": {
            "path": str(daily_basic_root),
            "files": len(list(daily_basic_root.glob("trade_date=*/data.parquet"))) if daily_basic_root.is_dir() else 0,
        },
        "csi300": {"path": str(index_path), "files": int(index_path.is_file())},
    }
    if not all(item["files"] > 0 for item in layouts.values()):
        return {
            "passed": False,
            "layouts": layouts,
            "error": "required canonical local-data layouts are missing",
        }

    connection = duckdb.connect(database=":memory:")
    try:
        connection.execute("set threads=2")
        connection.execute("set memory_limit='512MB'")
        equity_relation = (
            f"read_parquet('{_sql_path(equity_pattern)}', union_by_name=true, hive_partitioning=false)"
        )
        daily_basic_relation = (
            f"read_parquet('{_sql_path(daily_basic_pattern)}', union_by_name=true, hive_partitioning=false)"
        )
        index_relation = (
            f"read_parquet('{_sql_path(index_path)}', union_by_name=true, hive_partitioning=false)"
        )
        equity = _query_one(
            connection,
            f"""
            select
                count(*) as row_count,
                count(distinct cast(ts_code as varchar) || ':' || cast(trade_date as varchar)) as unique_rows,
                sum(case when ts_code is null or trade_date is null then 1 else 0 end) as null_keys,
                sum(case
                    when open is null or high is null or low is null or close is null
                      or cast(open as double) <= 0 or cast(high as double) <= 0
                      or cast(low as double) <= 0 or cast(close as double) <= 0
                      or cast(high as double) < greatest(cast(open as double), cast(close as double), cast(low as double))
                      or cast(low as double) > least(cast(open as double), cast(close as double), cast(high as double))
                    then 1 else 0 end) as invalid_ohlc,
                min(cast(trade_date as varchar)) as first_date,
                max(cast(trade_date as varchar)) as last_date,
                count(distinct ts_code) as symbols
            from {equity_relation}
            """,
        )
        daily_basic = _query_one(
            connection,
            f"""
            select
                count(*) as row_count,
                count(distinct cast(ts_code as varchar) || ':' || cast(trade_date as varchar)) as unique_rows,
                sum(case when ts_code is null or trade_date is null then 1 else 0 end) as null_keys,
                sum(case when pe_ttm is not null then 1 else 0 end) as pe_ttm_rows,
                min(cast(trade_date as varchar)) as first_date,
                max(cast(trade_date as varchar)) as last_date
            from {daily_basic_relation}
            """,
        )
        csi300 = _query_one(
            connection,
            f"""
            select
                count(*) as row_count,
                count(distinct cast(date as varchar)) as unique_rows,
                sum(case when date is null then 1 else 0 end) as null_keys,
                sum(case
                    when open is null or high is null or low is null or close is null
                      or cast(open as double) <= 0 or cast(high as double) <= 0
                      or cast(low as double) <= 0 or cast(close as double) <= 0
                      or cast(high as double) < greatest(cast(open as double), cast(close as double), cast(low as double))
                      or cast(low as double) > least(cast(open as double), cast(close as double), cast(high as double))
                    then 1 else 0 end) as invalid_ohlc,
                min(cast(date as varchar)) as first_date,
                max(cast(date as varchar)) as last_date
            from {index_relation}
            """,
        )

        schemas: dict[str, Any] = {"checked": 0, "errors": []}
        if deep:
            # Never descend into immutable release copies here. They are verified separately
            # against their own manifest and checksums, avoiding an unnecessary second full scan.
            parquet_files = sorted(
                path
                for path in data_dir.rglob("*.parquet")
                if path.is_file() and "releases" not in path.relative_to(data_dir).parts
            )
            schemas["total"] = len(parquet_files)
            for path in parquet_files:
                try:
                    if path.stat().st_size <= 0:
                        raise ValueError("zero-size parquet file")
                    schema = pl.scan_parquet(path).collect_schema()
                    if not schema:
                        raise ValueError("empty parquet schema")
                    schemas["checked"] += 1
                except Exception as exc:
                    schemas["errors"].append({"path": str(path), "error": str(exc)})
                    if len(schemas["errors"]) >= 100:
                        break
        else:
            schemas["skipped"] = True

        return {
            "passed": True,
            "layouts": layouts,
            "equity": equity,
            "dailyBasic": daily_basic,
            "csi300": csi300,
            "parquetMetadata": schemas,
        }
    except Exception as exc:
        return {"passed": False, "layouts": layouts, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        connection.close()


def _select_release_manifest(data_dir: Path, requested_release_id: str | None) -> Path:
    releases_root = data_dir / "releases"
    if requested_release_id:
        manifest_path = releases_root / requested_release_id / "manifest.json"
        if not manifest_path.is_file():
            raise ValueError(f"requested DataRelease is missing: {requested_release_id}")
        return manifest_path

    candidates = sorted(releases_root.glob("ds_*/manifest.json"))
    if not candidates:
        raise ValueError("no immutable DataRelease found under data/releases")

    def sort_key(path: Path) -> tuple[str, int]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            published = str(payload.get("publishedAt") or "")
        except Exception:
            published = ""
        return published, path.stat().st_mtime_ns

    return max(candidates, key=sort_key)


def _verify_data_release(data_dir: Path, requested_release_id: str | None) -> dict[str, Any]:
    checks = {
        "identityValid": False,
        "manifestSha256Valid": False,
        "lineageValid": False,
        "requiredComponentsValid": False,
        "checksumsBound": False,
        "frozenFilesValid": False,
        "barsPresent": False,
    }
    try:
        manifest_path = _select_release_manifest(data_dir, requested_release_id)
        release_root = manifest_path.parent.resolve()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("DataRelease manifest must be a JSON object")

        release_id = str(manifest.get("dataReleaseId") or "")
        if not release_id or release_root.name != release_id:
            raise ValueError("DataRelease directory and manifest identity do not match")
        if requested_release_id and release_id != requested_release_id:
            raise ValueError("resolved DataRelease does not match --data-release-id")

        identity = {
            "schemaVersion": manifest.get("schemaVersion"),
            "profile": manifest.get("profile"),
            "assetClass": manifest.get("assetClass"),
            "market": manifest.get("market"),
            "universe": manifest.get("universe"),
            "benchmark": manifest.get("benchmark"),
            "asOfTime": manifest.get("asOfTime"),
            "coverage": manifest.get("coverage"),
            "requiredComponents": manifest.get("requiredComponents"),
            "components": manifest.get("components"),
            "policies": manifest.get("policies") or {},
            "lineage": manifest.get("lineage") or {},
        }
        identity_sha = hashlib.sha256(_canonical_bytes(identity)).hexdigest()
        checks["identityValid"] = (
            str(manifest.get("identitySha256") or "") == identity_sha
            and release_id == f"ds_{identity_sha}"
        )

        manifest_without_sha = dict(manifest)
        declared_manifest_sha = str(manifest_without_sha.pop("manifestSha256", "") or "")
        calculated_manifest_sha = hashlib.sha256(
            _canonical_bytes(manifest_without_sha)
        ).hexdigest()
        checks["manifestSha256Valid"] = (
            bool(declared_manifest_sha) and declared_manifest_sha == calculated_manifest_sha
        )

        lineage_path = release_root / "lineage.json"
        lineage = manifest.get("lineage")
        stored_lineage = (
            json.loads(lineage_path.read_text(encoding="utf-8"))
            if lineage_path.is_file()
            else None
        )
        checks["lineageValid"] = (
            isinstance(lineage, dict) and bool(lineage) and stored_lineage == lineage
        )

        if str(BACKEND) not in sys.path:
            sys.path.insert(0, str(BACKEND))
        from app.services.data_releases import required_components_for_profile

        expected_roles = required_components_for_profile(str(manifest.get("profile") or ""))
        declared_required = frozenset(
            str(item) for item in (manifest.get("requiredComponents") or [])
        )
        components = manifest.get("components") or []
        actual_roles = frozenset(
            str(item.get("role") or "") for item in components if isinstance(item, dict)
        )
        checks["requiredComponentsValid"] = (
            declared_required == expected_roles and expected_roles <= actual_roles
        )

        checksums_path = release_root / "checksums.json"
        checksums = (
            json.loads(checksums_path.read_text(encoding="utf-8"))
            if checksums_path.is_file()
            else {}
        )
        checksum_files = checksums.get("files") if isinstance(checksums, dict) else {}
        checks["checksumsBound"] = bool(
            isinstance(checksum_files, dict)
            and checksums.get("dataReleaseId") == release_id
            and checksums.get("manifestSha256") == declared_manifest_sha
        )

        verified_files = 0
        frozen_files_valid = checks["checksumsBound"]
        bars_files: list[Path] = []
        for component in components:
            if not isinstance(component, dict):
                frozen_files_valid = False
                continue
            role = str(component.get("role") or "")
            for item in component.get("files") or []:
                if not isinstance(item, dict):
                    frozen_files_valid = False
                    continue
                relative = str(item.get("path") or "")
                frozen = (release_root / relative).resolve()
                try:
                    frozen.relative_to(release_root)
                except ValueError:
                    frozen_files_valid = False
                    continue
                expected_sha = str(item.get("sha256") or "").lower()
                if (
                    not relative
                    or frozen.is_symlink()
                    or not frozen.is_file()
                    or not expected_sha
                    or checksum_files.get(relative) != expected_sha
                    or _sha256_file(frozen) != expected_sha
                ):
                    frozen_files_valid = False
                    continue
                verified_files += 1
                if role == "bars" and frozen.suffix.lower() == ".parquet":
                    bars_files.append(frozen)

        checks["frozenFilesValid"] = bool(frozen_files_valid and verified_files > 0)
        checks["barsPresent"] = bool(bars_files)
        passed = all(checks.values())
        return {
            "passed": passed,
            "selection": "explicit" if requested_release_id else "latest-published",
            "dataReleaseId": release_id,
            "identitySha256": identity_sha,
            "manifestSha256": declared_manifest_sha,
            "profile": manifest.get("profile"),
            "coverage": manifest.get("coverage"),
            "asOfTime": manifest.get("asOfTime"),
            "lineage": lineage if isinstance(lineage, dict) else {},
            "releaseRoot": str(release_root),
            "manifestPath": str(manifest_path.resolve()),
            "barsFiles": [str(path) for path in bars_files],
            "verifiedFiles": verified_files,
            "checks": checks,
        }
    except Exception as exc:
        return {
            "passed": False,
            "requestedDataReleaseId": requested_release_id,
            "checks": checks,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _normalize_date(value: Any) -> str:
    text = str(value)
    if len(text) >= 10 and text[4] == "-":
        return text[:10]
    compact = "".join(char for char in text if char.isdigit())[:8]
    if len(compact) == 8:
        return f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"
    raise ValueError(f"invalid trade date: {value!r}")


def _parquet_relation(paths: list[Path]) -> str:
    if not paths:
        raise ValueError("no frozen bars parquet files were supplied")
    escaped = ", ".join(f"'{_sql_path(path)}'" for path in paths)
    return f"read_parquet([{escaped}], union_by_name=true, hive_partitioning=false)"


def _real_rows_for_smoke(
    bars_files: list[Path], requested_symbol: str | None, row_limit: int
) -> tuple[str, list[dict[str, str]]]:
    import duckdb

    relation = _parquet_relation(bars_files)
    connection = duckdb.connect(database=":memory:")
    try:
        raw_symbol = requested_symbol
        if raw_symbol:
            compact = raw_symbol.split(".", 1)[0]
            candidate = _query_one(
                connection,
                f"""
                select ts_code, count(*) as rows
                from {relation}
                where regexp_replace(cast(ts_code as varchar), '[^0-9]', '', 'g') = ?
                group by ts_code order by rows desc limit 1
                """,
                [compact],
            )
        else:
            candidate = _query_one(
                connection,
                f"""
                select ts_code, count(*) as rows
                from {relation}
                where open is not null and close is not null and vol is not null
                group by ts_code
                having count(*) >= ?
                order by rows desc, ts_code
                limit 1
                """,
                [row_limit],
            )
        if not candidate:
            raise RuntimeError(
                "no equity symbol in the frozen DataRelease bars has enough rows for the LEAN smoke test"
            )
        ts_code = str(candidate["ts_code"])
        cursor = connection.execute(
            f"""
            select trade_date, open, high, low, close, vol
            from {relation}
            where cast(ts_code as varchar) = ?
            order by trade_date desc
            limit ?
            """,
            [ts_code, row_limit],
        )
        raw_rows = cursor.fetchall()
    finally:
        connection.close()
    rows = [
        {
            "date": _normalize_date(item[0]),
            "open": str(item[1]),
            "high": str(item[2]),
            "low": str(item[3]),
            "close": str(item[4]),
            "volume": str(int(float(item[5] or 0))),
        }
        for item in reversed(raw_rows)
    ]
    return ts_code.split(".", 1)[0], rows


def _synthetic_spy_rows(start: date, end: date) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    current = start - timedelta(days=10)
    price = 300.0
    while current <= end + timedelta(days=5):
        if current.weekday() < 5:
            close = price + 0.25
            rows.append(
                {
                    "date": current.isoformat(),
                    "open": f"{price:.4f}",
                    "high": f"{close * 1.002:.4f}",
                    "low": f"{price * 0.998:.4f}",
                    "close": f"{close:.4f}",
                    "volume": "1000000",
                }
            )
            price = close
        current += timedelta(days=1)
    return rows


def _docker_ready(image: str, *, pull: bool) -> dict[str, Any]:
    if shutil.which("docker") is None:
        return {"passed": False, "error": "docker command not found", "image": image}
    info = subprocess.run(
        ["docker", "info"], capture_output=True, text=True, check=False, timeout=20
    )
    if info.returncode:
        return {
            "passed": False,
            "error": info.stderr.strip() or "docker daemon unavailable",
            "image": image,
        }
    inspect = subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    pulled = False
    if inspect.returncode and pull:
        result = subprocess.run(
            ["docker", "pull", image],
            capture_output=True,
            text=True,
            check=False,
            timeout=900,
        )
        if result.returncode:
            return {
                "passed": False,
                "error": result.stderr.strip() or "docker image pull failed",
                "image": image,
            }
        pulled = True
    elif inspect.returncode:
        return {
            "passed": False,
            "error": "pinned LEAN image is not present and pulling is disabled",
            "image": image,
        }
    return {"passed": True, "image": image, "pulled": pulled}


def _lean_smoke(
    data_release: dict[str, Any],
    *,
    symbol: str | None,
    row_limit: int,
    work_dir: Path,
    pull_image: bool,
) -> dict[str, Any]:
    bars_files = [Path(item) for item in data_release.get("barsFiles") or []]
    selected_symbol, rows = _real_rows_for_smoke(bars_files, symbol, row_limit)
    if len(rows) < min(60, row_limit):
        return {
            "passed": False,
            "symbol": selected_symbol,
            "error": f"only {len(rows)} frozen DataRelease rows available",
        }

    lean_data = work_dir / "Data"
    runtime = work_dir / "runtime"
    os.environ["LEAN_DATA_DIR"] = str(lean_data)
    os.environ["LEAN_RUNTIME_DIR"] = str(runtime)
    os.environ["LEAN_EXECUTION_BACKEND"] = "docker"
    os.environ["LEAN_DEPLOYMENT_MODE"] = "docker"
    os.environ["LEAN_API_AUTH_REQUIRED"] = "0"
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))

    from app.core.config import DEFAULT_DOCKER_IMAGE
    from app.lean_engine.data_writers import write_lean_daily_zip
    from app.runners.lean_runner import LeanRunner
    from app.services.lean_cache import ensure_lean_interest_rate_reference_data

    docker = _docker_ready(DEFAULT_DOCKER_IMAGE, pull=pull_image)
    if not docker["passed"]:
        return {"passed": False, "symbol": selected_symbol, "docker": docker}

    release_id = str(data_release["dataReleaseId"])
    manifest_sha = str(data_release["manifestSha256"])
    write_lean_daily_zip(
        selected_symbol,
        rows,
        f"data-release:{release_id}",
        overwrite=True,
        market="china",
    )
    start = date.fromisoformat(rows[0]["date"])
    end = date.fromisoformat(rows[-1]["date"])
    write_lean_daily_zip(
        "SPY",
        _synthetic_spy_rows(start, end),
        "local-data-certification-reference",
        overwrite=True,
        market="usa",
    )
    ensure_lean_interest_rate_reference_data()

    project_dir = work_dir / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    class_name = "LocalDataCertificationAlgorithm"
    (project_dir / "main.py").write_text(
        f"""from AlgorithmImports import *

class {class_name}(QCAlgorithm):
    def initialize(self):
        Market.Add("china", 101)
        self.set_start_date({start.year}, {start.month}, {start.day})
        self.set_end_date({end.year}, {end.month}, {end.day})
        self.set_cash(1000000)
        equity = self.add_equity("{selected_symbol}", Resolution.DAILY, "china", data_normalization_mode=DataNormalizationMode.RAW)
        self.symbol = equity.symbol
        self.set_benchmark(lambda time: 1)

    def on_data(self, data):
        if not self.portfolio.invested and data.contains_key(self.symbol):
            self.set_holdings(self.symbol, 0.5)
""",
        encoding="utf-8",
    )
    run_id = f"local-data-cert-{int(time.time())}"
    output = LeanRunner(timeout_seconds=300).run_backtest(
        run_id,
        {
            "ticker": selected_symbol,
            "assetClass": "equity",
            "market": "china",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "cash": 1_000_000,
            "dataReleaseId": release_id,
            "dataReleaseManifestSha256": manifest_sha,
        },
        work_dir / "runs" / run_id,
        output_callback=lambda _line: None,
        algorithm_path=project_dir / "main.py",
        algorithm_class=class_name,
        language="Python",
        project_dir=project_dir,
    )
    passed = bool(
        output.get("exit_code") == 0
        and output.get("result_json_path")
        and output.get("statistics")
    )
    return {
        "passed": passed,
        "dataReleaseId": release_id,
        "manifestSha256": manifest_sha,
        "lineage": data_release.get("lineage") or {},
        "source": "immutable-data-release-bars",
        "symbol": selected_symbol,
        "sourceRows": len(rows),
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "docker": docker,
        "exitCode": output.get("exit_code"),
        "resultJson": output.get("result_json_path"),
        "statistics": output.get("statistics"),
        "error": output.get("error"),
    }


def certify(args: argparse.Namespace) -> dict[str, Any]:
    data_dir = args.data_dir.expanduser().resolve()
    started = time.perf_counter()
    inventory = _inventory(data_dir, deep=not args.skip_deep)
    data_release = _verify_data_release(data_dir, args.data_release_id)
    thresholds = {
        "equityRows": args.min_equity_rows,
        "equityPartitions": args.min_equity_partitions,
        "dailyBasicRows": args.min_daily_basic_rows,
        "dailyBasicPartitions": args.min_daily_basic_partitions,
        "indexRows": args.min_index_rows,
    }
    checks: dict[str, bool] = {
        "dataDirectoryExists": data_dir.is_dir(),
        "inventoryReadable": bool(inventory.get("passed")),
        "dataReleaseResolved": bool(data_release.get("dataReleaseId")),
        "dataReleaseValid": bool(data_release.get("passed")),
    }
    if inventory.get("passed"):
        equity = inventory["equity"]
        daily_basic = inventory["dailyBasic"]
        csi300 = inventory["csi300"]
        checks.update(
            {
                "equityRows": int(equity["row_count"]) >= args.min_equity_rows,
                "equityPartitions": int(inventory["layouts"]["equity"]["files"])
                >= args.min_equity_partitions,
                "equityUniqueKeys": int(equity["row_count"]) == int(equity["unique_rows"]),
                "equityNonNullKeys": int(equity["null_keys"] or 0) == 0,
                "equityOhlcValid": int(equity["invalid_ohlc"] or 0) == 0,
                "dailyBasicRows": int(daily_basic["row_count"])
                >= args.min_daily_basic_rows,
                "dailyBasicPartitions": int(inventory["layouts"]["dailyBasic"]["files"])
                >= args.min_daily_basic_partitions,
                "dailyBasicUniqueKeys": int(daily_basic["row_count"])
                == int(daily_basic["unique_rows"]),
                "dailyBasicNonNullKeys": int(daily_basic["null_keys"] or 0) == 0,
                "dailyBasicPeTtmPresent": int(daily_basic["pe_ttm_rows"] or 0) > 0,
                "csi300Rows": int(csi300["row_count"]) >= args.min_index_rows,
                "csi300UniqueDates": int(csi300["row_count"])
                == int(csi300["unique_rows"]),
                "csi300OhlcValid": int(csi300["invalid_ohlc"] or 0) == 0,
            }
        )
        metadata = inventory.get("parquetMetadata") or {}
        if not args.skip_deep:
            checks["allParquetMetadataReadable"] = (
                not metadata.get("errors")
                and int(metadata.get("checked") or 0) == int(metadata.get("total") or 0)
            )

    lean: dict[str, Any]
    if args.skip_lean_smoke:
        lean = {
            "passed": True,
            "skipped": True,
            "dataReleaseId": data_release.get("dataReleaseId"),
            "manifestSha256": data_release.get("manifestSha256"),
        }
    elif all(checks.values()):
        work_dir = args.work_dir.expanduser().resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
        try:
            lean = _lean_smoke(
                data_release,
                symbol=args.symbol,
                row_limit=args.lean_rows,
                work_dir=work_dir,
                pull_image=not args.no_pull_image,
            )
        except Exception as exc:
            lean = {"passed": False, "error": f"{type(exc).__name__}: {exc}"}
        checks["frozenDataReleaseToLeanBacktest"] = bool(lean.get("passed"))
    else:
        lean = {"passed": False, "skipped": True, "reason": "data or DataRelease checks failed"}
        checks["frozenDataReleaseToLeanBacktest"] = False

    return {
        "schemaVersion": 2,
        "generatedAt": _utc_now(),
        "gitSha": _git_sha(),
        "dataDir": str(data_dir),
        "readOnlySource": True,
        "thresholds": thresholds,
        "passed": all(checks.values()),
        "checks": checks,
        "inventory": inventory,
        "dataRelease": data_release,
        "leanSmoke": lean,
        "durationSeconds": round(time.perf_counter() - started, 3),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Certify the mounted local market lake, immutable DataRelease identity/lineage, "
            "and a frozen DataRelease -> LEAN backtest path."
        )
    )
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument(
        "--data-release-id",
        help="Exact immutable DataRelease to certify; defaults to latest published release.",
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        default=ROOT / "web" / "runtime" / "audit" / "local-data-certification.json",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=ROOT / "web" / "runtime" / "local-data-certification",
    )
    parser.add_argument("--symbol")
    parser.add_argument("--lean-rows", type=int, default=160)
    parser.add_argument("--min-equity-rows", type=int, default=100_000)
    parser.add_argument("--min-equity-partitions", type=int, default=250)
    parser.add_argument("--min-daily-basic-rows", type=int, default=100_000)
    parser.add_argument("--min-daily-basic-partitions", type=int, default=250)
    parser.add_argument("--min-index-rows", type=int, default=250)
    parser.add_argument("--skip-deep", action="store_true")
    parser.add_argument("--skip-lean-smoke", action="store_true")
    parser.add_argument("--no-pull-image", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = certify(args)
    except Exception as exc:
        result = {
            "schemaVersion": 2,
            "generatedAt": _utc_now(),
            "gitSha": _git_sha(),
            "dataDir": str(args.data_dir),
            "passed": False,
            "failure": {"type": type(exc).__name__, "detail": str(exc)},
        }
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
