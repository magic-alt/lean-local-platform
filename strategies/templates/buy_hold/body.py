        self.has_bought = False

    def on_data(self, data):
        if self.has_bought or not data.contains_key(self.symbol):
            return
        self.ashare_execution.target_percent(self.symbol, 1) if self.ashare_execution else self.set_holdings(self.symbol, 1)
        self.has_bought = True
