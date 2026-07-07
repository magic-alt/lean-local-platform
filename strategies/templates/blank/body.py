        self.set_warm_up(1, self.resolution)

    def on_data(self, data):
        if self.is_warming_up:
            return
        # Write custom strategy logic here.
