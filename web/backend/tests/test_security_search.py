from fastapi.testclient import TestClient

from app.db import init_db
from app.db import db, utc_now
from app.main import app
from app.services.ashare_repository import upsert_security
from app.services.instrument_identity import upsert_instrument_identifiers
from app.services.market_repository import get_instrument, upsert_instrument


def test_security_search_matches_company_alias_pinyin_and_market_labels(monkeypatch):
    init_db()
    upsert_security(symbol="600519", name="贵州茅台", exchange="SSE", listed_date="2001-08-27")
    upsert_instrument(
        symbol="600519",
        name="600519",
        asset_class="equity",
        market="china",
        venue="china",
        exchange="SSE",
        currency="CNY",
        listed_date="2026-07-14",
        source="test:coverage-derived",
    )
    upsert_instrument(
        symbol="00700",
        name="腾讯控股",
        asset_class="equity",
        market="hongkong",
        venue="hongkong",
        exchange="HKEX",
        currency="HKD",
        metadata={"aliases": ["腾讯"]},
        source="test",
    )
    instrument = get_instrument("00700", market="hongkong", venue="hongkong")
    assert instrument is not None
    assert instrument["currency"] == "HKD"
    upsert_instrument(
        symbol="AAPL",
        name="Apple Inc.",
        asset_class="equity",
        market="usa",
        venue="usa",
        exchange="NASDAQ",
        currency="USD",
        metadata={"aliases": ["苹果"]},
        source="test",
    )

    client = TestClient(app)
    company_response = client.get("/api/securities/search", params={"market": "china", "keyword": "茅台"})
    assert company_response.status_code == 200
    company = company_response.json()["items"][0]
    assert company["symbol"] == "600519"
    assert company["name"] == "贵州茅台"
    assert company["marketLabel"] == "A股"
    assert company["listedDate"] == "2001-08-27"
    assert company["matchField"] == "name"

    from app.services import security_search

    class FakeStyle:
        FIRST_LETTER = "initials"

    monkeypatch.setattr(security_search, "Style", FakeStyle)
    monkeypatch.setattr(
        security_search,
        "lazy_pinyin",
        lambda value, style=None: (
            (["g", "z", "m", "t"] if style == "initials" else ["gui", "zhou", "mao", "tai"])
            if value == "贵州茅台"
            else [value]
        ),
    )
    pinyin_response = client.get("/api/securities/search", params={"market": "china", "keyword": "gzmt"})
    assert pinyin_response.status_code == 200
    assert pinyin_response.json()["items"][0]["symbol"] == "600519"
    assert pinyin_response.json()["items"][0]["matchField"] == "pinyin"

    alias_response = client.get("/api/securities/search", params={"market": "all", "keyword": "苹果"})
    assert alias_response.status_code == 200
    assert alias_response.json()["items"][0]["symbol"] == "AAPL"
    assert alias_response.json()["items"][0]["marketLabel"] == "美股"
    assert alias_response.json()["items"][0]["matchField"] == "alias"

    hk_response = client.get("/api/securities/search", params={"market": "hongkong", "keyword": "00700.HK"})
    assert hk_response.status_code == 200
    assert hk_response.json()["items"][0]["symbol"] == "00700"
    assert hk_response.json()["items"][0]["marketLabel"] == "H股"
    assert hk_response.json()["items"][0]["matchType"] == "exact"


def test_security_profile_separates_master_source_from_identifiers_and_reports_coverage():
    init_db()
    upsert_security(
        symbol="000001",
        name="平安银行",
        exchange="SZSE",
        listed_date="1991-04-03",
        industry="银行",
    )
    upsert_instrument(
        symbol="000001",
        name="平安银行",
        asset_class="equity",
        market="china",
        venue="china",
        exchange="SZSE",
        currency="CNY",
        listed_date="1991-04-03",
        source="tushare:stock_basic",
    )
    upsert_instrument_identifiers(symbols=["000001"], source="akshare")
    from app.services import market_lake

    market_lake.upsert_rows(
        [{"symbol": "000001", "trade_date": "2026-07-18", "open": 10, "high": 11,
          "low": 9, "close": 10.5, "prev_close": 10, "pct_change": 5, "volume": 1000}],
        kind="bars", source="tushare",
    )
    market_lake.upsert_rows(
        [{"symbol": "000001", "trade_date": "2026-07-18", "is_tradeable": 1,
          "is_suspended": 0, "limit_up": 11.55, "limit_down": 9.45,
          "can_buy": 1, "can_sell": 1}],
        kind="trade_status", data_type="status", source="tushare:stk_limit",
    )
    market_lake.upsert_rows(
        [{"symbol": "000001", "trade_date": "2026-07-18", "adj_factor": 123.45}],
        kind="adjustment_factor", data_type="factor", source="tushare",
    )

    response = TestClient(app).get("/api/securities/000001/profile", params={"market": "china"})
    assert response.status_code == 200
    profile = response.json()
    assert profile["name"] == "平安银行"
    assert profile["listedDate"] == "1991-04-03"
    assert profile["industry"] == "银行"
    assert profile["masterSource"] == "tushare:stock_basic"
    assert profile["masterSource"] != profile["identifiers"][0]["source"]
    assert {item["key"] for item in profile["coverage"]} == {"daily", "trade_status", "adjustment_factors"}
    assert profile["latestTradeStatus"]["trade_date"] == "2026-07-18"
    assert profile["quote"]["close"] == 10.5
    assert profile["quote"]["change"] == 0.5
    assert profile["adjustmentHistory"][0]["adj_factor"] == 123.45
    assert profile["limitHistory"][0]["limit_up"] == 11.55
