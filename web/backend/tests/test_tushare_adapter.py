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
