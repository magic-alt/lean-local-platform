        self.has_bought = False

    def on_data(self, data):
        if self.has_bought or not has_fresh_data(data, self.symbol):
            return
            self.ashare_execution.target_percent_moo(self.symbol, 1, "buy_hold_entry") if self.ashare_execution else self.set_holdings(self.symbol, 1)
        self.has_bought = True
