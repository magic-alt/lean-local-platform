from AlgorithmImports import *


class WindowsNativeCoreSmokeAlgorithm(QCAlgorithm):
    def initialize(self):
        Market.Add("china", 101)
        self.set_start_date(2024, 1, 2)
        self.set_end_date(2024, 1, 5)
        self.set_account_currency("CNY")
        self.set_cash(100000)
        ticker = self.get_parameter("ticker") or "999999"
        equity = self.add_equity(
            ticker,
            Resolution.DAILY,
            "china",
            data_normalization_mode=DataNormalizationMode.RAW,
        )
        equity.set_fee_model(ConstantFeeModel(0))
        self.symbol = equity.symbol
        self.order_submitted = False

    def on_data(self, data):
        if self.order_submitted or not data.contains_key(self.symbol):
            return
        self.market_order(self.symbol, 100, tag="windows-native-core-v1")
        self.order_submitted = True
