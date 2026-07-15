        self.set_warm_up(1, self.resolution)

    def on_data(self, data):
        if not has_fresh_data(data, self.symbol) or self.is_warming_up:
            return
        # Write custom strategy logic here.
