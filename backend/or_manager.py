# backend/or_manager.py

import datetime as dt

class ORManager:
    def __init__(self):
        self.or_data = {}

    def update(self, symbol, candle):
        time = candle["date"].time()

        if symbol not in self.or_data:
            self.or_data[symbol] = {
                "high": candle["high"],
                "low": candle["low"],
                "locked": False,
                "date": candle["date"].date()
            }

        data = self.or_data[symbol]

        if data["locked"]:
            return

        if dt.time(9,15) <= time <= dt.time(9,30):
            data["high"] = max(data["high"], candle["high"])
            data["low"] = min(data["low"], candle["low"])

        if time > dt.time(9,30):
            data["locked"] = True

    def get_or(self, symbol):
        return self.or_data.get(symbol, None)