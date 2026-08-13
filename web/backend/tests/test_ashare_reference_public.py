def configure_temp_db(tmp_path, monkeypatch):
    import app.db as db_module

    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(db_module, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(db_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(db_module, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(db_module, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(db_module, "RESEARCH_DIR", tmp_path / "research")
    monkeypatch.setattr(db_module, "OBJECT_STORE_DIR", tmp_path / "object-store")
    monkeypatch.setattr(db_module, "REPORTS_DIR", tmp_path / "reports")
    db_module.init_db()
    return db_module


class FakeFrame:
    def __init__(self, records):
        self.records = records
        self.empty = not records

    def to_dict(self, orient):
        assert orient == "records"
        return self.records


class FakeAk:
    def stock_info_sh_delist(self, **kwargs):
        return FakeFrame([{"公司代码": "600001", "公司简称": "ST退市样本", "上市日期": "1998-01-22", "暂停上市日期": "2009-12-29"}])

    def stock_info_sz_delist(self, **kwargs):
        return FakeFrame([{"证券代码": "000003", "证券简称": "PT金田Ａ", "上市日期": "1991-01-14", "终止上市日期": "2002-06-14"}])

    def stock_zh_a_st_em(self):
        return FakeFrame([{"代码": "600001", "名称": "ST退市样本"}])

    def stock_zh_a_stop_em(self):
        raise RuntimeError("primary stop source unavailable")

    def stock_tfp_em(self, date):
        assert date == "20260706"
        return FakeFrame([{"代码": "000003", "名称": "PT金田Ａ", "停牌时间": 1783296000000.0, "预计复牌时间": ""}])

    def stock_dividend_cninfo(self, symbol):
        dates = {"600519": "2024-07-01", "000001": "2024-06-28", "300750": "2024-06-20"}
        return FakeFrame([{"除权日": dates[symbol], "派息比例": 30.0, "送股比例": 1.0, "转增比例": 2.0}])


def test_public_reference_import_helpers_write_canonical_tables(tmp_path, monkeypatch):
    db_module = configure_temp_db(tmp_path, monkeypatch)

    from app.services.ashare_repository import import_security_master, import_trade_status, upsert_corporate_actions
    from scripts.import_ashare_reference_public import (
        _mark_security_st,
        fetch_delisted_records,
        fetch_dividend_records,
        fetch_st_status_records,
        fetch_suspended_status_records,
    )

    fake = FakeAk()
    delisted, errors = fetch_delisted_records(fake)
    assert errors == []
    assert len(delisted) == 2
    import_security_master(delisted, source="akshare:delist", universe_code="ALL_A")

    st_records, st_symbols, errors = fetch_st_status_records(fake, "2026-07-06")
    assert errors == []
    _mark_security_st(st_symbols)
    import_trade_status(st_records, source="akshare:st")

    suspended, errors = fetch_suspended_status_records(fake, "2026-07-06")
    assert errors == [{"source": "stock_zh_a_stop_em", "error": "primary stop source unavailable"}]
    import_trade_status(suspended, source="akshare:suspended")

    actions, errors = fetch_dividend_records(fake, ["600519", "000001", "300750"], "2024-01-01", "2024-12-31")
    assert errors == []
    upsert_corporate_actions(actions, source="akshare:stock_dividend_cninfo")

    with db_module.db() as connection:
        security = connection.execute("select status, delisted_date, is_st from securities where symbol = '600001'").fetchone()
        action = connection.execute("select cash_dividend, stock_dividend from corporate_actions where symbol = '600519'").fetchone()
        action_symbols = connection.execute("select distinct symbol from corporate_actions order by symbol").fetchall()

    assert security["status"] == "delisted"
    assert security["delisted_date"] == "2009-12-29"
    assert security["is_st"] == 1
    from app.services.ashare_repository import effective_trade_status
    suspended_row = effective_trade_status("000003", "2026-07-06")
    assert suspended_row and suspended_row["is_suspended"] == 1
    assert suspended_row["can_buy"] == 0
    assert suspended_row["can_sell"] == 0
    assert action["cash_dividend"] == 3.0
    assert round(action["stock_dividend"], 6) == 0.3
    assert [row["symbol"] for row in action_symbols] == ["000001", "300750", "600519"]
