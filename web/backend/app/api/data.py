from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .common import dispatch_task
from ..core.config import UPLOADS_DIR
from ..core.errors import LeanWebError
from ..db import db, rows_to_dicts, utc_now
from ..lean import list_local_symbols, rows_from_csv, write_lean_daily_zip
from ..services.data import data_providers, fetch_and_import_symbol, record_data_asset
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
    provider: str = "yahoo"
    apiKey: str | None = None
    outputsize: str = "compact"
    overwrite: bool = False


class BatchDataFetchRequest(BaseModel):
    symbols: list[str] = Field(min_length=1)
    provider: str = "yahoo"
    apiKey: str | None = None
    outputsize: str = "compact"
    overwrite: bool = False


@router.get("/symbols")
def symbols():
    items = list_local_symbols()
    return {"symbols": items, "count": len(items)}


@router.get("/data-assets")
def data_assets():
    with db() as connection:
        rows = connection.execute("select * from data_assets order by created_at desc").fetchall()
    return rows_to_dicts(rows)


@router.get("/data/providers")
def providers():
    return data_providers()


@router.post("/data/fetch")
def fetch_data(request: DataFetchRequest):
    try:
        return fetch_and_import_symbol(
            request.symbol,
            request.provider,
            overwrite=request.overwrite,
            api_key=request.apiKey,
            outputsize=request.outputsize,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/data/fetch-batch")
def fetch_batch(request: BatchDataFetchRequest):
    symbols = [symbol.upper().strip() for symbol in request.symbols if symbol.strip()]
    task = create_task(
        "data_fetch",
        f"Fetch {len(symbols)} symbol(s)",
        {
            "symbols": symbols,
            "provider": request.provider,
            "apiKey": request.apiKey,
            "outputsize": request.outputsize,
            "overwrite": request.overwrite,
        },
    )
    dispatch_task(fetch_data_batch_task.s(task["id"]), task["id"])
    return task


@router.post("/data/import-csv")
async def import_csv(
    symbol: str = Form(...),
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
        metadata = write_lean_daily_zip(symbol, rows, f"csv:{file.filename}", overwrite=overwrite)
        return record_data_asset(metadata)
    except LeanWebError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/data/fetch-alpha-vantage")
def fetch_alpha_vantage(request: AlphaVantageRequest):
    try:
        return fetch_and_import_symbol(
            request.symbol,
            "alpha_vantage",
            overwrite=request.overwrite,
            api_key=request.apiKey,
            outputsize=request.outputsize,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
