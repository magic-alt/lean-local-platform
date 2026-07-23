import gzip
import json
import uuid

from fastapi.testclient import TestClient

from app.db import db, init_db, utc_now
from app.main import app
from app.services.db_object_store import put_bytes


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
    with db() as connection:
        connection.executemany(
            """
            insert into adjustment_factors (symbol,trade_date,adj_factor,source,batch_id)
            values (?, '2026-07-17', 1.0, 'tushare', 'test')
            """,
            [("600519",), ("1600519",)],
        )

    response = TestClient(app).get(
        "/api/data/dataset-preview/adj_factor",
        params={"keyword": "SH600519", "limit": 20},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["count"] == 1
    assert result["items"][0]["symbol"] == "600519"


def test_index_archive_preview_reads_compressed_batch_without_row_json():
    init_db()
    payload = gzip.compress(json.dumps([
        {"ts_code": "000300.SH", "trade_date": "20260717", "close": 4000.5, "pct_chg": 1.2},
        {"ts_code": "000905.SH", "trade_date": "20260716", "close": 6200.0, "pct_chg": -0.5},
    ]).encode("utf-8"), mtime=0)
    stored = put_bytes("provider-raw", "test/index-daily.json.gz", payload)
    now = utc_now()
    with db() as connection:
        connection.execute(
            """
            insert into provider_raw_archives
                (id,provider,dataset_key,run_id,object_id,row_count,payload_sha256,
                 archive_sha256,uncompressed_size,compressed_size,compression,created_at)
            values (?, 'tushare','index_daily','test',?,2,'payload','archive',100,?,'gzip',?)
            """,
            (str(uuid.uuid4()), stored["id"], len(payload), now),
        )

    response = TestClient(app).get(
        "/api/data/dataset-preview/index_daily",
        params={"keyword": "000300", "limit": 20},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["storage"] == "compressed_archive"
    assert result["count"] == 1
    assert result["items"][0]["trade_date"] == "2026-07-17"
    assert result["items"][0]["close"] == 4000.5


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
