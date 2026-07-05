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
                    "suspend_date": "20240103",
                    "resume_date": "20240104",
                    "ann_date": "20240102",
                    "suspend_reason": "重大事项",
                    "reason_type": "event",
                }
            ]
        )

    def dividend(self, **kwargs):
        return FakeFrame(
            [
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
