from collections import Counter

from fastapi.testclient import TestClient


def test_checked_in_tushare_contract_covers_the_official_market_domains():
    from app.services.tushare_contracts import contract_snapshot

    snapshot = contract_snapshot()
    contracts = snapshot["contracts"]

    assert snapshot["contractVersion"] == "2026-08-12.1"
    assert len(contracts) == 139
    assert Counter(item["assetClass"] for item in contracts) == {
        "equity": 100,
        "index": 21,
        "future": 15,
        "option": 3,
    }
    assert Counter(item["status"] for item in contracts) == {"active": 137, "retired": 2}
    assert all(item["contractComplete"] for item in contracts)
    assert all(item["naturalKey"] for item in contracts)
    assert len({item["sourceTable"] for item in contracts}) == len(contracts)
    assert all(item["fields"] for item in contracts)


def test_contract_catalog_and_generated_source_tables_are_complete():
    from app.db import db, init_db
    from app.services.commercial_market_schema import commercial_schema_status
    from app.services.tushare_contracts import sync_contract_catalog

    init_db()
    first = sync_contract_catalog()
    second = sync_contract_catalog()
    status = commercial_schema_status()

    assert first == second == {"providers": 1, "datasets": 139, "contracts": 139}
    assert status["coreTables"] == {"expected": 16, "present": 16, "missing": []}
    assert status["sourceTables"] == {"expected": 139, "present": 139}
    with db() as connection:
        dataset_count = connection.execute(
            "select count(*) as count from provider_datasets_v2"
        ).fetchone()["count"]
        contract_count = connection.execute(
            "select count(*) as count from dataset_contract_versions_v2"
        ).fetchone()["count"]
    assert dataset_count == 139
    assert contract_count == 139


def test_typed_source_writer_keeps_revisions_and_handles_large_lookups(monkeypatch):
    from app.db import db, init_db
    from app.services import tushare_typed_source

    monkeypatch.setenv("LEAN_TUSHARE_TYPED_SOURCE_WRITES", "1")
    persist_typed_source_rows = tushare_typed_source.persist_typed_source_rows

    init_db()
    initial_rows = [
        {
            "ts_code": f"{index:06d}.SZ",
            "com_name": f"Company {index}",
            "reg_capital": "1234.50000000",
            "setup_date": "20200102",
            "employees": "100",
        }
        for index in range(501)
    ]
    first = persist_typed_source_rows("stock_company", initial_rows, "batch-1")
    unchanged = persist_typed_source_rows("stock_company", initial_rows, "batch-2")
    revised = persist_typed_source_rows(
        "stock_company",
        [{**initial_rows[0], "com_name": "Renamed Company"}],
        "batch-3",
    )

    assert first == {"scanned": 501, "inserted": 501, "revised": 0, "unchanged": 0}
    assert unchanged == {"scanned": 501, "inserted": 0, "revised": 0, "unchanged": 501}
    assert revised == {"scanned": 1, "inserted": 0, "revised": 1, "unchanged": 0}
    with db() as connection:
        versions = connection.execute(
            """
            select `_revision_no`,`_is_current`,`com_name`,`setup_date`,`employees`
            from `src_tushare_stock_company`
            where `ts_code`='000000.SZ'
            order by `_revision_no`
            """
        ).fetchall()
        total = connection.execute(
            "select count(*) as count from `src_tushare_stock_company`"
        ).fetchone()["count"]
    assert total == 502
    assert [row["_revision_no"] for row in versions] == [1, 2]
    assert [row["_is_current"] for row in versions] == [0, 1]
    assert versions[1]["com_name"] == "Renamed Company"
    assert versions[1]["setup_date"] == "2020-01-02"
    assert versions[1]["employees"] == 100


def test_public_contract_api_filters_and_exposes_typed_fields():
    from app.main import app

    response = TestClient(app).get(
        "/api/data/contracts",
        params={"assetClass": "option", "includeFields": "true"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 3
    assert {item["assetClass"] for item in payload["items"]} == {"option"}
    basic = next(item for item in payload["items"] if item["datasetKey"] == "opt_basic")
    assert basic["naturalKey"] == ["ts_code"]
    assert {field["name"] for field in basic["fields"]} >= {
        "ts_code",
        "exercise_price",
        "maturity_date",
    }

    invalid = TestClient(app).get("/api/data/contracts", params={"assetClass": "crypto"})
    assert invalid.status_code == 400
