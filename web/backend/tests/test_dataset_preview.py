import gzip
import json
import uuid

from fastapi.testclient import TestClient

from app.db import db, init_db, utc_now
from app.main import app
from app.services import dataset_preview as dataset_preview_service
from app.services.db_object_store import put_bytes
from app.services.market_repository import upsert_market_daily_bars
from app.services import market_lake


def _store_archive(dataset: str, rows: list[dict[str, object]]) -> None:
    payload = gzip.compress(json.dumps(rows).encode("utf-8"), mtime=0)
    stored = put_bytes("provider-raw", f"test/{dataset}.json.gz", payload)
    with db() as connection:
        connection.execute(
            """
            insert into provider_raw_archives
                (id,provider,dataset_key,run_id,object_id,row_count,payload_sha256,
                 archive_sha256,uncompressed_size,compressed_size,compression,created_at)
            values (?, 'tushare',?,'test',?,?,'payload','archive',100,?,'gzip',?)
            """,
            (str(uuid.uuid4()), dataset, stored["id"], len(rows), len(payload), utc_now()),
        )


def test_trade_calendar_preview_filters_and_pages_canonical_rows():
    init_db()
    with db() as connection:
        connection.executemany(
            """
            insert into trade_calendar
                (market,trade_date,is_open,prev_trade_date,next_trade_date,source,batch_id)
            values ('china',?,?,?,?, 'tushare:trade_cal:SSE','test')
            """,
            [
                ("2026-07-17", 1, "2026-07-16", "2026-07-20"),
                ("2026-07-18", 0, "2026-07-17", "2026-07-20"),
                ("2026-07-20", 1, "2026-07-17", "2026-07-21"),
            ],
        )

    response = TestClient(app).get(
        "/api/data/dataset-preview/trade_cal",
        params={"startDate": "2026-07-18", "endDate": "2026-07-20", "limit": 1},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["storage"] == "canonical_table"
    assert result["count"] == 2
    assert result["items"][0]["trade_date"] == "2026-07-20"


def test_symbol_preview_uses_normalized_exact_match():
    init_db()
    market_lake.upsert_rows(
        [{"symbol": symbol, "trade_date": "2026-07-17", "adj_factor": 1.0, "batch_id": "test"}
         for symbol in ("600519", "1600519")],
        kind="adjustment_factor", data_type="factor", source="tushare",
    )

    response = TestClient(app).get(
        "/api/data/dataset-preview/adj_factor",
        params={"keyword": "SH600519", "limit": 20},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["count"] == 1
    assert result["items"][0]["symbol"] == "600519"


def test_daily_basic_parquet_and_dividend_metadata_previews():
    init_db()
    market_lake.upsert_rows(
        [{"symbol": "600519", "trade_date": "2026-07-17", "pe_ttm": 21.5, "batch_id": "test"}],
        kind="daily_basic", data_type="metric", source="tushare:daily_basic",
    )
    with db() as connection:
        connection.execute(
            """
            insert into corporate_actions
                (symbol,ex_date,action_type,cash_dividend,stock_dividend,source,batch_id,created_at)
            values ('600519','2026-06-20','dividend',2.5,0.1,'tushare:dividend','test',?)
            """,
            (utc_now(),),
        )

    client = TestClient(app)
    basic = client.get("/api/data/dataset-preview/daily_basic", params={"keyword": "pe_ttm"})
    dividend = client.get("/api/data/dataset-preview/dividend", params={"keyword": "SH600519"})

    assert basic.status_code == dividend.status_code == 200
    assert basic.json()["storage"] == dividend.json()["storage"] == "canonical_table"
    assert basic.json()["items"][0]["value"] == 21.5
    assert dividend.json()["items"][0]["cash_dividend"] == 2.5


def test_index_daily_preview_reads_full_canonical_history_instead_of_latest_archive():
    init_db()
    _store_archive("index_daily", [
        {"ts_code": "000001.SH", "trade_date": "20260717", "close": 3500.5, "pct_chg": 1.2},
    ])
    upsert_market_daily_bars(
        [
            {"trade_date": "2026-07-16", "open": 3490, "high": 3510, "low": 3480, "close": 3500, "volume": 100},
            {"trade_date": "2026-07-17", "open": 3500, "high": 3530, "low": 3495, "close": 3525, "volume": 120},
        ],
        symbol="000001",
        asset_class="index",
        market="china",
        venue="china",
        source="tushare",
    )

    response = TestClient(app).get(
        "/api/data/dataset-preview/index_daily",
        params={"keyword": "000001.SH", "limit": 20},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["storage"] == "canonical_table"
    assert result["count"] == 2
    assert [item["trade_date"] for item in result["items"]] == ["2026-07-17", "2026-07-16"]
    assert result["items"][0]["ts_code"] == "000001.SH"
    assert result["items"][0]["trade_date"] == "2026-07-17"
    assert result["items"][0]["close"] == 3525


def test_futures_preview_only_returns_contracts_tradable_on_market_date(monkeypatch):
    init_db()
    _store_archive("fut_basic", [
        {"ts_code": "IF2608.CFX", "list_date": "2026-01-01", "last_ddate": "2026-08-21"},
        {"ts_code": "IF2607.CFX", "list_date": "2026-01-01", "last_ddate": "2026-07-17"},
        {"ts_code": "IF2612.CFX", "list_date": "2026-08-01", "last_ddate": "2026-12-18"},
        {"ts_code": "IFL.CFX"},
    ])
    monkeypatch.setattr(dataset_preview_service, "_current_market_date", lambda: "2026-07-31")

    response = TestClient(app).get("/api/data/dataset-preview/fut_basic")

    assert response.status_code == 200
    result = response.json()
    assert result["scope"] == "currently_tradable"
    assert result["asOfDate"] == "2026-07-31"
    assert result["count"] == 1
    assert [item["ts_code"] for item in result["items"]] == ["IF2608.CFX"]


def test_options_preview_uses_last_trading_date_before_expiry_fallback(monkeypatch):
    init_db()
    _store_archive("opt_basic", [
        {
            "ts_code": "10010001.SH",
            "list_date": "2026-06-01",
            "last_ddate": "2026-07-30",
            "last_edate": "2026-08-01",
            "maturity_date": "2026-08-01",
        },
        {
            "ts_code": "10010002.SH",
            "list_date": "2026-06-01",
            "last_edate": "2026-08-27",
            "maturity_date": "2026-08-27",
        },
        {
            "ts_code": "10010003.SH",
            "list_date": "2026-08-01",
            "last_edate": "2026-09-24",
        },
    ])
    monkeypatch.setattr(dataset_preview_service, "_current_market_date", lambda: "2026-07-31")

    response = TestClient(app).get("/api/data/dataset-preview/opt_basic")

    assert response.status_code == 200
    result = response.json()
    assert result["scope"] == "currently_tradable"
    assert result["asOfDate"] == "2026-07-31"
    assert result["count"] == 1
    assert [item["ts_code"] for item in result["items"]] == ["10010002.SH"]


def test_dataset_preview_rejects_unsupported_dataset():
    init_db()
    response = TestClient(app).get("/api/data/dataset-preview/not_a_dataset")
    assert response.status_code == 400


def test_csv_import_template_has_required_ohlcv_columns():
    init_db()
    response = TestClient(app).get("/api/data/import-csv/template")
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    lines = response.content.decode("utf-8-sig").splitlines()
    assert lines[0] == "timestamp,open,high,low,close,volume"
    assert len(lines) >= 2
