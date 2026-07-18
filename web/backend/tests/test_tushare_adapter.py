import pytest


class FakeFrame:
    def __init__(self, records):
        self._records = records
        self.empty = not records

    def to_dict(self, orient):
        assert orient == "records"
        return self._records


class DailyOnlyPro:
    def __init__(self):
        self.daily_calls = []

    def daily(self, **kwargs):
        self.daily_calls.append(kwargs)
        return FakeFrame(
            [
                {
                    "ts_code": "600519.SH",
                    "trade_date": "20240103",
                    "open": 101.0,
                    "high": 103.0,
                    "low": 100.0,
                    "close": 102.0,
                    "pre_close": 100.0,
                    "pct_chg": 2.0,
                    "vol": 12.5,
                    "amount": 130.0,
                },
                {
                    "ts_code": "600519.SH",
                    "trade_date": "20240102",
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "pre_close": 99.5,
                    "pct_chg": 0.5,
                    "vol": 10.0,
                    "amount": 100.0,
                },
            ]
        )

    def adj_factor(self, **kwargs):
        raise RuntimeError("no permission")

    def stk_limit(self, **kwargs):
        raise RuntimeError("no permission")


class WindowedDailyPro:
    def __init__(self):
        self.daily_calls = []
        self.adjustment_calls = []
        self.limit_calls = []

    def daily(self, **kwargs):
        self.daily_calls.append(kwargs)
        trade_date = kwargs["start_date"]
        return FakeFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": trade_date,
                    "open": 10.0,
                    "high": 10.5,
                    "low": 9.8,
                    "close": 10.2,
                    "pre_close": 10.0,
                    "pct_chg": 2.0,
                    "vol": 10.0,
                    "amount": 100.0,
                }
            ]
        )

    def adj_factor(self, **kwargs):
        self.adjustment_calls.append(kwargs)
        return FakeFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": kwargs["start_date"],
                    "adj_factor": 1.0,
                }
            ]
        )

    def stk_limit(self, **kwargs):
        self.limit_calls.append(kwargs)
        return FakeFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": kwargs["start_date"],
                    "up_limit": 11.0,
                    "down_limit": 9.0,
                }
            ]
        )


class StockBasicPro:
    def stock_basic(self, **kwargs):
        return FakeFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "symbol": "000001",
                    "name": "平安银行",
                    "industry": float("nan"),
                    "list_date": "19910403",
                    "delist_date": "",
                    "list_status": "L",
                },
                {
                    "ts_code": "000002.SZ",
                    "symbol": "000002",
                    "name": "*ST测试",
                    "industry": "Real Estate",
                    "list_date": "19910129",
                    "delist_date": "",
                    "list_status": "L",
                },
                {
                    "ts_code": "000003.SZ",
                    "symbol": "000003",
                    "name": "退市样本",
                    "industry": "Other",
                    "list_date": "19910114",
                    "delist_date": "20200101",
                    "list_status": "D",
                },
                {
                    "ts_code": "T600018.SH",
                    "symbol": "T600018",
                    "name": "历史无效代码",
                    "industry": "Other",
                    "list_date": "19910114",
                    "delist_date": "20200101",
                    "list_status": "D",
                },
            ]
        )


class SectorFallbackPro:
    def dc_index(self, **kwargs):
        return FakeFrame(
            [
                {"ts_code": "DC001", "name": "半导体概念"},
                {"ts_code": "DC002", "name": "存储芯片"},
                {"ts_code": "DC003", "name": "CPO概念"},
                {"ts_code": "DC004", "name": "PCB概念"},
            ]
        )

    def ths_index(self, **kwargs):
        return FakeFrame([{"ts_code": "886044.TI", "name": "液冷服务器"}])

    def dc_daily(self, ts_code, **kwargs):
        return FakeFrame(
            [{"trade_date": "20260716", "open": 100, "high": 102, "low": 99, "close": 101, "vol": 10, "amount": 20}]
        )

    def ths_daily(self, ts_code, **kwargs):
        assert ts_code == "886044.TI"
        return FakeFrame(
            [{"trade_date": "20260716", "open": 200, "high": 205, "low": 198, "close": 203, "vol": 15}]
        )


def test_tushare_stock_basic_marks_st_and_delisted():
    from app.services.tushare_adapter import TushareAdapter

    rows = TushareAdapter(pro=StockBasicPro()).stock_basic(["L"])

    by_symbol = {row["symbol"]: row for row in rows}
    assert "T600018" not in by_symbol
    assert by_symbol["000001"]["is_st"] is False
    assert by_symbol["000001"]["industry"] is None
    assert by_symbol["000002"]["is_st"] is True
    assert by_symbol["000003"]["status"] == "delisted"
    assert by_symbol["000003"]["delisted_date"] == "2020-01-01"


def test_sector_topics_continue_from_dc_to_ths_and_preserve_canonical_keyword():
    from app.services.ashare_tech_insights import SECTOR_TOPICS
    from app.services.tushare_adapter import TushareAdapter

    rows = TushareAdapter(pro=SectorFallbackPro()).sector_daily_rows(
        SECTOR_TOPICS,
        "2026-07-01",
        "2026-07-16",
    )

    by_keyword = {item["keyword"]: item for item in rows}
    assert set(by_keyword) == {"半导体", "存储", "CPO", "PCB", "AI服务器"}
    assert by_keyword["AI服务器"]["code"] == "886044.TI"
    assert by_keyword["AI服务器"]["matchedName"] == "液冷服务器"
    assert by_keyword["AI服务器"]["matchedKeyword"] == "液冷服务器"
    assert by_keyword["AI服务器"]["matchRule"] == "alias"
    assert by_keyword["AI服务器"]["source"] == "tushare:ths_daily"


def test_tushare_daily_rows_degrades_when_only_pro_daily_is_allowed():
    from app.services.tushare_adapter import TushareAdapter

    pro = DailyOnlyPro()
    rows = TushareAdapter(pro=pro).daily_rows("600519", "2024-01-02", "2024-01-03")

    assert pro.daily_calls[0]["ts_code"] == "600519.SH"
    assert pro.daily_calls[0]["start_date"] == "20240102"
    assert pro.daily_calls[0]["end_date"] == "20240103"
    assert [row["date"] for row in rows] == ["2024-01-02", "2024-01-03"]
    assert rows[0]["volume"] == 1000
    assert rows[0]["amount"] == 100000.0
    assert rows[0]["adj_factor"] == 1.0
    assert rows[0]["limitUp"] is None
    assert rows[0]["canBuy"] is None


def test_tushare_full_history_is_downloaded_in_bounded_date_windows():
    from app.services.tushare_adapter import TushareAdapter

    pro = WindowedDailyPro()
    rows = TushareAdapter(pro=pro).daily_rows("000001", "1990-01-01", "2026-07-16")

    assert len(pro.daily_calls) == 4
    assert len(pro.adjustment_calls) == 4
    assert len(pro.limit_calls) == 4
    assert pro.daily_calls[0]["start_date"] == "19900101"
    assert pro.daily_calls[-1]["end_date"] == "20260716"
    assert [row["date"] for row in rows] == [
        call["start_date"][:4] + "-" + call["start_date"][4:6] + "-" + call["start_date"][6:]
        for call in pro.daily_calls
    ]
    assert all(row["adj_factor_verified"] for row in rows)


def test_tushare_rejects_qfq_hfq_to_avoid_adjustment_mixing():
    from app.core.errors import LeanWebError
    from app.services.tushare_adapter import TushareAdapter

    with pytest.raises(LeanWebError, match="raw daily bars"):
        TushareAdapter(pro=DailyOnlyPro()).daily_rows("600519", "2024-01-02", "2024-01-03", adjust="qfq")


class ResearchPro(DailyOnlyPro):
    def daily_basic(self, **kwargs):
        return FakeFrame(
            [
                {
                    "ts_code": "600519.SH",
                    "trade_date": "20240102",
                    "turnover_rate": 1.2,
                    "pe_ttm": 20.5,
                    "pb": 5.1,
                    "total_mv": 2500.0,
                    "circ_mv": 2000.0,
                    "free_share": 100.0,
                }
            ]
        )

    def suspend_d(self, **kwargs):
        return FakeFrame(
            [
                {
                    "ts_code": "600519.SH",
                    "trade_date": "20240103",
                    "suspend_timing": None,
                    "suspend_type": "S",
                }
            ]
        )

    def dividend(self, **kwargs):
        return FakeFrame(
            [
                {
                    "ts_code": "600519.SH",
                    "end_date": "20231231",
                    "ann_date": "nan",
                    "ex_date": "nan",
                    "record_date": "nan",
                    "div_listdate": "nan",
                    "cash_div_tax": 10.0,
                    "div_proc": "预案",
                },
                {
                    "ts_code": "600519.SH",
                    "end_date": "20231231",
                    "ann_date": "20240402",
                    "ex_date": "20240510",
                    "cash_div_tax": 30.0,
                    "stk_bo_rate": 1.0,
                    "stk_co_rate": 2.0,
                    "div_proc": "实施",
                }
            ]
        )

    def index_weight(self, **kwargs):
        return FakeFrame(
            [
                {
                    "index_code": "000300.SH",
                    "con_code": "600519.SH",
                    "trade_date": "20240102",
                    "weight": 4.2,
                }
            ]
        )

    def income(self, **kwargs):
        return FakeFrame(
            [
                {
                    "ts_code": "600519.SH",
                    "ann_date": "20240402",
                    "f_ann_date": "20240403",
                    "end_date": "20231231",
                    "revenue": 100.0,
                    "n_income": 20.0,
                    "update_flag": "1",
                }
            ]
        )


def test_tushare_research_rows_normalize_units_dates_and_fields():
    from app.services.tushare_adapter import TushareAdapter

    adapter = TushareAdapter(pro=ResearchPro())

    factors = adapter.daily_basic_rows("600519", "2024-01-02", "2024-01-02")
    assert factors[0]["trade_date"] == "2024-01-02"
    assert factors[0]["factors"]["pe_ttm"] == 20.5
    assert factors[0]["factors"]["total_mv_cny"] == 25000000.0
    assert factors[0]["factors"]["free_share_shares"] == 1000000.0

    suspensions = adapter.suspend_rows("600519", "2024-01-02", "2024-01-05")
    assert suspensions[0]["suspend_date"] == "2024-01-03"
    assert suspensions[0]["resume_date"] == "2024-01-04"
    assert suspensions[0]["source"] == "tushare:suspend_d"

    dividends = adapter.dividend_rows("600519", "2024-05-01", "2024-05-31")
    assert dividends[0]["ex_date"] == "2024-05-10"
    assert dividends[0]["cash_dividend"] == 3.0
    assert dividends[0]["stock_dividend"] == 0.30000000000000004

    weights = adapter.index_weight_rows("000300", "2024-01-02", "2024-01-02")
    assert weights == [
        {
            "universe_code": "CSI300",
            "symbol": "600519",
            "trade_date": "2024-01-02",
            "weight": 4.2,
            "source": "tushare:index_weight",
        }
    ]

    financials = adapter.income_rows("600519", "2023-01-01", "2024-12-31")
    assert financials[0]["statement_type"] == "income"
    assert financials[0]["report_date"] == "2023-12-31"
    assert financials[0]["effective_date"] == "2024-04-03"
    assert financials[0]["fields"] == {"revenue": 100.0, "n_income": 20.0}


class HongKongPro:
    def hk_basic(self, **kwargs):
        return FakeFrame([
            {"ts_code": "00700.HK", "name": "腾讯控股", "list_status": "L", "list_date": "20040616", "trade_unit": 100, "curr_type": "HKD"}
        ])

    def hk_tradecal(self, **kwargs):
        return FakeFrame([
            {"cal_date": "20240102", "is_open": 1, "pretrade_date": "20231229"},
            {"cal_date": "20240103", "is_open": 0, "pretrade_date": "20240102"},
        ])

    def hk_daily(self, **kwargs):
        return FakeFrame([
            {"ts_code": "00700.HK", "trade_date": "20240102", "open": 290, "high": 300, "low": 288, "close": 299, "pre_close": 292, "vol": 123456, "amount": 36000000}
        ])


def test_tushare_hong_kong_basics_calendar_and_daily_rows():
    from app.services.tushare_adapter import TushareAdapter

    adapter = TushareAdapter(pro=HongKongPro())
    basics = adapter.hk_basic(["L"])
    assert basics[0]["symbol"] == "00700"
    assert basics[0]["currency"] == "HKD"
    assert basics[0]["lot_size"] == 100

    calendar = adapter.hk_trade_calendar("2024-01-02", "2024-01-03")
    assert calendar[0]["trade_date"] == "2024-01-02"
    assert calendar[0]["is_open"] is True

    rows = adapter.hk_daily_rows("00700", "2024-01-02", "2024-01-02")
    assert rows[0]["date"] == "2024-01-02"
    assert rows[0]["volume"] == 123456
    assert rows[0]["source"] == "tushare:hk_daily"
