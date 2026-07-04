from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .common import dispatch_task
from ..core.config import UPLOADS_DIR
from ..core.errors import LeanWebError
from ..db import db, rows_to_dicts, utc_now
from ..lean import (
    list_local_symbols,
    market_key,
    normalize_symbol,
    rows_from_csv,
    write_lean_crypto_daily_zip,
    write_lean_daily_zip,
    write_lean_future_daily_zip,
)
from ..services.data import (
    asset_classes,
    data_providers,
    fetch_and_import_symbol,
    local_data_index,
    markets,
    record_data_asset,
    symbols_for_asset,
)
from ..services.market_data import mirror_rows, query_bars
from ..services.tasks import create_task
from ..tasks.worker import fetch_data_batch_task

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
    provider: str = "yahoo"
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
    provider: str = "yahoo"
    apiKey: str | None = None
    outputsize: str = "compact"
    startDate: str | None = None
    endDate: str | None = None
    adjust: str = ""
    overwrite: bool = False


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
def search_securities(market: str = "usa", keyword: str = ""):
    key = market_key(market)
    query = keyword.strip()
    local = list_local_symbols(key)
    matches = [
        {"symbol": symbol, "market": key, "name": symbol, "hasLocalData": True}
        for symbol in local
        if not query or query.upper() in symbol
    ][:50]
    if query:
        try:
            normalized = normalize_symbol(query, key).upper()
            if normalized not in {item["symbol"] for item in matches}:
                matches.insert(0, {"symbol": normalized, "market": key, "name": normalized, "hasLocalData": normalized in local})
        except Exception:
            pass
    return {"items": matches, "count": len(matches)}


@router.get("/data-assets")
def data_assets():
    with db() as connection:
        rows = connection.execute("select * from data_assets order by created_at desc").fetchall()
    return rows_to_dicts(rows)


@router.get("/data/providers")
def providers():
    return data_providers()


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
    startDate: str | None = None,
    endDate: str | None = None,
    limit: int = 500,
):
    try:
        return query_bars(
            asset_class=assetClass,
            symbol=symbol,
            venue=venue or market,
            resolution=resolution,
            data_type=dataType,
            start_date=startDate,
            end_date=endDate,
            limit=limit,
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
        rows = rows_from_csv(upload_path, dateCol, openCol, highCol, lowCol, closeCol, volumeCol)
        if assetClass == "crypto":
            metadata = write_lean_crypto_daily_zip(symbol, rows, f"csv:{file.filename}", overwrite=overwrite, venue=venue or market, data_type=dataType)
        elif assetClass == "future":
            metadata = write_lean_future_daily_zip(symbol, rows, f"csv:{file.filename}", overwrite=overwrite, venue=venue or market, data_type=dataType)
        else:
            metadata = write_lean_daily_zip(symbol, rows, f"csv:{file.filename}", overwrite=overwrite, market=market)
            metadata.update({"asset_class": "equity", "venue": market, "resolution": "daily", "data_type": "trade"})
        try:
            metadata["clickhouse"] = mirror_rows(metadata, rows)
        except Exception as exc:
            metadata["clickhouse"] = {"enabled": True, "inserted": 0, "error": str(exc)}
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
