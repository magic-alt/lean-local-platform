from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .common import dispatch_task
from ..core.config import UPLOADS_DIR
from ..core.errors import LeanWebError
from ..db import db, rows_to_dicts, utc_now
from ..lean_engine.data_writers import (
    rows_from_csv,
    write_lean_crypto_daily_zip,
    write_lean_daily_zip,
    write_lean_future_daily_zip,
)
from ..lean_engine.symbols import (
    market_key,
    normalize_symbol,
)
from ..services.data import (
    attach_database_objects,
    asset_classes,
    data_providers,
    provider_availability,
    fetch_and_import_symbol,
    import_ashare_research_data,
    local_data_index,
    markets,
    record_data_asset,
    symbols_for_asset,
)
from ..services.data_provider_manager import DATA_PROVIDER_MANAGER
from ..services.data_coverage import ashare_coverage, benchmark_coverage, symbol_coverage
from ..services.market_data import mirror_rows, query_bars, query_database_bars
from ..services.parquet_lake import export_market_daily_bars, list_datasets, parquet_consistency_report, query_duckdb_bars, rebuild_all_market_parquet
from ..services.ashare_multisource import compare_ashare_daily_sources, compare_ashare_daily_sources_batch, list_quality_reports
from ..services.free_data_pipeline import import_ashare_daily_sample
from ..services.intraday import import_intraday_bars
from ..services.instrument_identity import identifier_coverage, identifiers_for_symbol
from ..services.market_repository import upsert_market_daily_bars
from ..services.db_object_store import put_file
from ..services.source_gate import DATA_SOURCE_PRIORITY, PRIMARY_DATA_SOURCE, require_source_allowed, source_certification
from ..services.security_search import search_securities as search_security_catalog
from ..services.tasks import create_task
from ..services import data_sync
from ..tasks.worker import fetch_data_batch_task, sync_all_data_task

router = APIRouter(prefix="/api", tags=["data"])


class AlphaVantageRequest(BaseModel):
    symbol: str
    apiKey: str | None = None
    outputsize: str = "compact"
    overwrite: bool = False


class DataFetchRequest(BaseModel):
    symbol: str
    assetClass: str = "equity"
    market: str = "usa"
    venue: str | None = None
    resolution: str = "daily"
    dataType: str = "trade"
    provider: str = "auto"
    apiKey: str | None = None
    outputsize: str = "compact"
    startDate: str | None = None
    endDate: str | None = None
    adjust: str = ""
    overwrite: bool = False


class BatchDataFetchRequest(BaseModel):
    symbols: list[str] = Field(min_length=1)
    assetClass: str = "equity"
    market: str = "usa"
    venue: str | None = None
    resolution: str = "daily"
    dataType: str = "trade"
    provider: str = "auto"
    apiKey: str | None = None
    outputsize: str = "compact"
    startDate: str | None = None
    endDate: str | None = None
    adjust: str = ""
    overwrite: bool = False


class ParquetExportRequest(BaseModel):
    assetClass: str = "equity"
    market: str = "china"
    venue: str | None = "china"
    resolution: str = "daily"
    dataType: str = "trade"
    adjust: str = "raw"
    providerSource: str = PRIMARY_DATA_SOURCE
    allowResearchSource: bool = False
    startDate: str | None = None
    endDate: str | None = None


class ParquetRebuildRequest(BaseModel):
    assetClass: str | None = None
    market: str | None = None
    venue: str | None = None
    resolution: str | None = None
    dataType: str | None = None
    adjust: str | None = None
    sources: list[str] | None = None
    includeResearchSources: bool = False
    startDate: str | None = None
    endDate: str | None = None
    continueOnError: bool = True
    persistReport: bool = True


class ParquetConsistencyRequest(BaseModel):
    assetClass: str | None = None
    market: str | None = None
    venue: str | None = None
    resolution: str | None = None
    dataType: str | None = None
    adjust: str | None = None
    sources: list[str] | None = None
    includeResearchSources: bool = False
    persist: bool = True


class AshareDailyCompareRequest(BaseModel):
    symbol: str
    sources: list[str] = Field(default_factory=lambda: list(DATA_SOURCE_PRIORITY))
    startDate: str | None = None
    endDate: str | None = None
    adjust: str = "raw"
    priceAbsTolerance: float = 0.02
    priceRelToleranceBps: float = 5.0
    volumeRelTolerancePct: float = 5.0
    persist: bool = True


class AshareDailyCompareBatchRequest(AshareDailyCompareRequest):
    symbol: str | None = None
    symbols: list[str] = Field(min_length=1)
    persistSymbolReports: bool = True


class AshareDailySampleImportRequest(BaseModel):
    symbols: list[str] = Field(min_length=1)
    startDate: str
    endDate: str
    providers: list[str] = Field(default_factory=lambda: list(DATA_SOURCE_PRIORITY))
    adjust: str = "raw"
    primaryProvider: str = PRIMARY_DATA_SOURCE
    exportParquet: bool = True
    compareSources: bool = True
    continueOnError: bool = True


class IntradayImportRequest(BaseModel):
    symbol: str
    assetClass: str = "equity"
    market: str = "china"
    venue: str | None = None
    frequency: str = "5m"
    dataType: str = "trade"
    adjust: str = "raw"
    source: str = "manual"
    records: list[dict[str, Any]] = Field(min_length=1)


class DataSyncRequest(BaseModel):
    datasets: list[str] | None = None


@router.get("/symbols")
def symbols(
    market: str = "usa",
    assetClass: str = "equity",
    venue: str | None = None,
    resolution: str = "daily",
    dataType: str = "trade",
):
    items = symbols_for_asset(assetClass, venue=venue, market=market, resolution=resolution, data_type=dataType)
    return {"symbols": items, "count": len(items)}


@router.get("/securities/search")
def search_securities(market: str = "all", keyword: str = "", limit: int = 50):
    return search_security_catalog(keyword=keyword, market=market, limit=limit)


@router.get("/data-assets")
def data_assets(
    status: str | None = None,
    includeSuperseded: bool = True,
    limit: int = 500,
    offset: int = 0,
    paged: bool = False,
):
    clauses = []
    values: list[Any] = []
    if status:
        clauses.append("status = ?")
        values.append(status)
    elif not includeSuperseded:
        clauses.append("coalesce(status, 'active') = 'active'")
    where = f"where {' and '.join(clauses)}" if clauses else ""
    bounded_limit = max(1, min(int(limit), 1000))
    bounded_offset = max(0, int(offset))
    with db() as connection:
        count = connection.execute(f"select count(*) as count from data_assets {where}", values).fetchone()["count"]
        rows = connection.execute(
            f"select * from data_assets {where} order by created_at desc, id desc limit ? offset ?",
            [*values, bounded_limit, bounded_offset],
        ).fetchall()
    items = rows_to_dicts(rows)
    if paged:
        return {"items": items, "count": count, "limit": bounded_limit, "offset": bounded_offset}
    return items


@router.get("/data/providers")
def providers(includeAvailability: bool = False):
    if includeAvailability:
        return provider_availability()
    return data_providers()


@router.get("/data/providers/availability")
def data_provider_availability(provider: str | None = None):
    return provider_availability(provider)


@router.get("/data/catalog")
def data_catalog():
    return data_sync.catalog_payload()


@router.get("/data/sync-runs")
def data_sync_runs(limit: int = 20):
    return {"items": data_sync.list_sync_runs(limit), "limit": limit}


@router.post("/data/sync-runs")
def create_data_sync_run(request: DataSyncRequest):
    try:
        run = data_sync.create_sync_run(requested=request.datasets)
        task = create_task(
            "data_sync",
            "Update all TuShare data",
            {"runId": run["id"], "datasets": request.datasets or []},
            related_id=run["id"],
        )
        with db() as connection:
            connection.execute("update data_sync_runs set task_id=? where id=?", (task["id"], run["id"]))
        dispatch_task(sync_all_data_task.s(task["id"], run["id"]), task["id"])
        return data_sync.sync_run(run["id"])
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/data/sync-runs/{run_id}")
def data_sync_run(run_id: str):
    item = data_sync.sync_run(run_id)
    if not item:
        raise HTTPException(status_code=404, detail="Data sync run not found.")
    return item


@router.post("/data/sync-runs/{run_id}/cancel")
def cancel_data_sync_run(run_id: str):
    try:
        return data_sync.request_cancel(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/data/sync-runs/{run_id}/resume")
def resume_data_sync_run(run_id: str):
    try:
        run = data_sync.prepare_resume(run_id)
        task = create_task("data_sync", "Resume TuShare data update", {"runId": run_id}, related_id=run_id)
        with db() as connection:
            connection.execute("update data_sync_runs set task_id=? where id=?", (task["id"], run_id))
        dispatch_task(sync_all_data_task.s(task["id"], run_id), task["id"])
        return data_sync.sync_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/asset-classes")
def available_asset_classes():
    return asset_classes()


@router.get("/data/files")
def data_files(assetClass: str | None = None, venue: str | None = None):
    items = local_data_index(assetClass, venue)
    return {"items": items, "count": len(items)}


@router.get("/data/query")
def query_data(
    symbol: str,
    assetClass: str = "equity",
    venue: str | None = None,
    market: str | None = None,
    resolution: str = "daily",
    dataType: str = "trade",
    source: str = "clickhouse",
    providerSource: str | None = None,
    providerMode: str = "strict",
    allowResearchSource: bool = False,
    adjust: str = "raw",
    startDate: str | None = None,
    endDate: str | None = None,
    limit: int = 500,
):
    try:
        asset_class = assetClass.strip().lower()
        query_market = market.strip().lower() if market else None
        query_venue = venue.strip().lower() if venue else None
        query_source = source.strip().lower()
        provider_input = (providerSource or "").strip().lower()
        auto_provider = provider_input in {"", "auto"}
        strict_provider = providerMode.strip().lower() != "auto" and not auto_provider
        provider_source = None if auto_provider else require_source_allowed(providerSource, allow_research_source=allowResearchSource)

        def resolve_symbol(raw: str) -> str:
            raw_value = raw.strip()
            if not raw_value:
                return raw_value
            if asset_class == "equity":
                for hint in [query_venue, query_market]:
                    if hint:
                        return normalize_symbol(raw_value, hint)
                if raw_value.startswith(("SH", "SZ", "SS", "BJ", "sh", "sz", "ss", "bj")) or "." in raw_value:
                    return normalize_symbol(raw_value, "china")
                if raw_value.replace(".", "").isdigit() and len(raw_value) == 6:
                    return normalize_symbol(raw_value, "china")
            return raw_value.strip().upper()

        resolved_symbol = resolve_symbol(symbol)

        def provider_chain() -> list[str | None]:
            if provider_source and strict_provider:
                return [provider_source]
            if asset_class == "equity":
                chain = DATA_PROVIDER_MANAGER.chain(
                    provider_source or "auto",
                    market=query_market or query_venue or "china",
                    asset_class=asset_class,
                    start_date=startDate,
                    end_date=endDate,
                    strict=False,
                )
                return chain or [provider_source]
            return [provider_source]

        def query_one(selected_source: str | None) -> dict[str, Any]:
            if query_source in {"duckdb", "parquet"}:
                return query_duckdb_bars(
                    asset_class=asset_class,
                    symbol=resolved_symbol,
                    market=market,
                    venue=venue,
                    resolution=resolution,
                    data_type=dataType,
                    provider_source=selected_source,
                    adjust=adjust or "raw",
                    start_date=startDate,
                    end_date=endDate,
                    limit=limit,
                )
            query = query_database_bars if query_source in {"mysql", "database", "local"} else query_bars
            return query(
                asset_class=asset_class,
                symbol=resolved_symbol,
                market=query_market,
                venue=query_venue,
                resolution=resolution,
                data_type=dataType,
                provider_source=selected_source,
                start_date=startDate,
                end_date=endDate,
                limit=limit,
            )

        attempts = []
        payload: dict[str, Any] | None = None
        selected_provider = provider_source
        for candidate in provider_chain():
            current = query_one(candidate)
            attempts.append({"source": candidate or "any", "status": "success" if current.get("count", 0) else "empty", "rows": current.get("count", 0)})
            payload = current
            selected_provider = candidate
            if current.get("count", 0) or strict_provider:
                break
        if payload is None:
            payload = query_one(provider_source)
        payload["query"] = {
            "symbolInput": symbol,
            "symbol": resolved_symbol,
            "assetClass": asset_class,
            "market": query_market,
            "venue": query_venue,
        }
        payload["providerSource"] = selected_provider
        payload["providerMode"] = "auto" if auto_provider or not strict_provider else "strict"
        payload["sourceAttempts"] = attempts
        payload["sourceCertification"] = source_certification(selected_provider, asset_class=assetClass, market=market or venue or "china", venue=venue or market)
        return payload
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/data/parquet/export")
def export_parquet_data(request: ParquetExportRequest):
    try:
        provider_source = require_source_allowed(request.providerSource, allow_research_source=request.allowResearchSource)
        return export_market_daily_bars(
            asset_class=request.assetClass,
            market=request.market,
            venue=request.venue,
            resolution=request.resolution,
            data_type=request.dataType,
            adjust=request.adjust,
            source=provider_source,
            start_date=request.startDate,
            end_date=request.endDate,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/data/parquet/datasets")
def parquet_datasets():
    return {"items": list_datasets()}


@router.post("/data/parquet/rebuild")
def rebuild_parquet_data(request: ParquetRebuildRequest):
    try:
        sources = [require_source_allowed(source, allow_research_source=request.includeResearchSources) for source in request.sources] if request.sources else None
        return rebuild_all_market_parquet(
            asset_class=request.assetClass,
            market=request.market,
            venue=request.venue,
            resolution=request.resolution,
            data_type=request.dataType,
            adjust=request.adjust,
            sources=sources,
            include_research_sources=request.includeResearchSources,
            start_date=request.startDate,
            end_date=request.endDate,
            continue_on_error=request.continueOnError,
            persist_report=request.persistReport,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/data/parquet/consistency")
def parquet_consistency(request: ParquetConsistencyRequest):
    try:
        sources = [require_source_allowed(source, allow_research_source=request.includeResearchSources) for source in request.sources] if request.sources else None
        return parquet_consistency_report(
            asset_class=request.assetClass,
            market=request.market,
            venue=request.venue,
            resolution=request.resolution,
            data_type=request.dataType,
            adjust=request.adjust,
            sources=sources,
            include_research_sources=request.includeResearchSources,
            persist=request.persist,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/data/quality/ashare/daily/compare")
def compare_ashare_daily_data(request: AshareDailyCompareRequest):
    try:
        return compare_ashare_daily_sources(
            symbol=request.symbol,
            start_date=request.startDate,
            end_date=request.endDate,
            sources=request.sources,
            adjust=request.adjust,
            price_abs_tolerance=request.priceAbsTolerance,
            price_rel_tolerance_bps=request.priceRelToleranceBps,
            volume_rel_tolerance_pct=request.volumeRelTolerancePct,
            persist=request.persist,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/data/quality/ashare/daily/compare-batch")
def compare_ashare_daily_data_batch(request: AshareDailyCompareBatchRequest):
    try:
        return compare_ashare_daily_sources_batch(
            symbols=request.symbols,
            start_date=request.startDate,
            end_date=request.endDate,
            sources=request.sources,
            adjust=request.adjust,
            price_abs_tolerance=request.priceAbsTolerance,
            price_rel_tolerance_bps=request.priceRelToleranceBps,
            volume_rel_tolerance_pct=request.volumeRelTolerancePct,
            persist=request.persist,
            persist_symbol_reports=request.persistSymbolReports,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/data/quality/reports")
def data_quality_reports(limit: int = 100):
    return {"items": list_quality_reports(limit=limit)}


@router.get("/data/coverage/ashare")
def data_coverage_ashare(
    symbols: str,
    benchmark: str = "000300",
    source: str | None = None,
    startDate: str = "2026-06-01",
    endDate: str = "2026-07-13",
):
    selected = [item.strip() for item in symbols.split(",") if item.strip()]
    return ashare_coverage(symbols=selected, benchmark=benchmark, source=source, start_date=startDate, end_date=endDate)


@router.get("/data/coverage/symbol/{symbol}")
def data_coverage_symbol(
    symbol: str,
    source: str | None = None,
    startDate: str = "2026-06-01",
    endDate: str = "2026-07-13",
):
    return symbol_coverage(symbol, source=source, start_date=startDate, end_date=endDate)


@router.get("/data/coverage/benchmark/{symbol}")
def data_coverage_benchmark(
    symbol: str,
    source: str | None = None,
    startDate: str = "2026-06-01",
    endDate: str = "2026-07-13",
):
    return benchmark_coverage(symbol, source=source, start_date=startDate, end_date=endDate)


@router.get("/data/identifiers/coverage")
def data_identifier_coverage(symbols: str | None = None):
    selected = [item.strip() for item in (symbols or "").split(",") if item.strip()] or None
    return identifier_coverage(selected)


@router.get("/data/identifiers/{symbol}")
def data_identifiers(symbol: str):
    return identifiers_for_symbol(symbol)


@router.post("/data/free/ashare/daily/import-sample")
def import_free_ashare_daily_sample(request: AshareDailySampleImportRequest):
    try:
        return import_ashare_daily_sample(
            symbols=request.symbols,
            start_date=request.startDate,
            end_date=request.endDate,
            providers=request.providers,
            adjust=request.adjust,
            primary_provider=request.primaryProvider,
            export_parquet=request.exportParquet,
            compare_sources=request.compareSources,
            continue_on_error=request.continueOnError,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/data/intraday/import")
def import_intraday_data(request: IntradayImportRequest):
    try:
        return import_intraday_bars(
            request.records,
            symbol=request.symbol,
            asset_class=request.assetClass,
            market=request.market,
            venue=request.venue,
            frequency=request.frequency,
            data_type=request.dataType,
            adjust=request.adjust,
            source=request.source,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/markets")
def available_markets():
    return markets()


@router.post("/data/fetch")
def fetch_data(request: DataFetchRequest):
    try:
        return fetch_and_import_symbol(
            request.symbol,
            request.provider,
            market=request.market,
            asset_class=request.assetClass,
            venue=request.venue,
            resolution=request.resolution,
            data_type=request.dataType,
            overwrite=request.overwrite,
            api_key=request.apiKey,
            outputsize=request.outputsize,
            start_date=request.startDate,
            end_date=request.endDate,
            adjust=request.adjust,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/data/fetch-batch")
def fetch_batch(request: BatchDataFetchRequest):
    if request.assetClass == "equity":
        market = market_key(request.market)
        symbols = [normalize_symbol(symbol, market).upper() for symbol in request.symbols if symbol.strip()]
    else:
        market = request.venue or request.market
        symbols = [symbol.strip().upper().replace("/", "").replace("-", "") for symbol in request.symbols if symbol.strip()]
    task = create_task(
        "data_fetch",
        f"Fetch {len(symbols)} symbol(s)",
        {
            "symbols": symbols,
            "assetClass": request.assetClass,
            "market": market,
            "venue": request.venue,
            "resolution": request.resolution,
            "dataType": request.dataType,
            "provider": request.provider,
            "apiKey": request.apiKey,
            "outputsize": request.outputsize,
            "startDate": request.startDate,
            "endDate": request.endDate,
            "adjust": request.adjust,
            "overwrite": request.overwrite,
        },
    )
    dispatch_task(fetch_data_batch_task.s(task["id"]), task["id"])
    return task


@router.post("/data/import-csv")
async def import_csv(
    symbol: str = Form(...),
    assetClass: str = Form("equity"),
    market: str = Form("usa"),
    venue: str = Form(""),
    dataType: str = Form("trade"),
    overwrite: bool = Form(False),
    dateCol: str = Form("timestamp"),
    openCol: str = Form("open"),
    highCol: str = Form("high"),
    lowCol: str = Form("low"),
    closeCol: str = Form("close"),
    volumeCol: str = Form("volume"),
    file: UploadFile = File(...),
):
    try:
        upload_path = UPLOADS_DIR / f"{utc_now().replace(':', '').replace('.', '')}-{file.filename}"
        upload_path.parent.mkdir(parents=True, exist_ok=True)
        upload_path.write_bytes(await file.read())
        put_file("uploads", upload_path.name, upload_path, metadata={"filename": file.filename, "asset_class": assetClass, "symbol": symbol})
        rows = rows_from_csv(upload_path, dateCol, openCol, highCol, lowCol, closeCol, volumeCol)
        if assetClass == "crypto":
            metadata = write_lean_crypto_daily_zip(symbol, rows, f"csv:{file.filename}", overwrite=overwrite, venue=venue or market, data_type=dataType)
        elif assetClass == "future":
            metadata = write_lean_future_daily_zip(symbol, rows, f"csv:{file.filename}", overwrite=overwrite, venue=venue or market, data_type=dataType)
        elif assetClass == "equity" and market_key(market) == "china":
            return import_ashare_research_data(
                symbol=normalize_symbol(symbol, "china"),
                provider="csv",
                market="china",
                rows=rows,
                source=f"csv:{file.filename}",
                overwrite=overwrite,
                adjust="raw",
                outputsize="",
                asset_class="equity",
                venue="china",
                resolution="daily",
                data_type="trade",
                start_date=None,
                end_date=None,
            )
        else:
            metadata = write_lean_daily_zip(symbol, rows, f"csv:{file.filename}", overwrite=overwrite, market=market)
            metadata.update({"asset_class": "equity", "venue": market, "resolution": "daily", "data_type": "trade"})
        upsert_market_daily_bars(
            rows,
            symbol=metadata.get("symbol") or symbol,
            asset_class=metadata.get("asset_class") or assetClass,
            market=market if assetClass == "equity" else (venue or market),
            venue=metadata.get("venue") or venue or market,
            source=f"csv:{file.filename}",
            resolution=metadata.get("resolution") or "daily",
            data_type=metadata.get("data_type") or dataType,
            adjust="raw",
        )
        try:
            metadata["clickhouse"] = mirror_rows(metadata, rows)
        except Exception as exc:
            metadata["clickhouse"] = {"enabled": True, "inserted": 0, "error": str(exc)}
        attach_database_objects(metadata)
        return record_data_asset(metadata)
    except LeanWebError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/data/fetch-alpha-vantage")
def fetch_alpha_vantage(request: AlphaVantageRequest):
    try:
        return fetch_and_import_symbol(
            request.symbol,
            "alpha_vantage",
            market="usa",
            overwrite=request.overwrite,
            api_key=request.apiKey,
            outputsize=request.outputsize,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
