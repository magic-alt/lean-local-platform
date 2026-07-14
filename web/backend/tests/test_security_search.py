from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app
from app.services.ashare_repository import upsert_security
from app.services.market_repository import upsert_instrument


def test_security_search_matches_company_alias_pinyin_and_market_labels(monkeypatch):
    init_db()
    upsert_security(symbol="600519", name="贵州茅台", exchange="SSE", listed_date="2001-08-27")
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
