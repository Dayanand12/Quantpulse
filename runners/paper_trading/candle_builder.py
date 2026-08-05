# live/candle_builder.py

import datetime as dt


class CandleBuilder:
    def __init__(self, symbols):
        self.symbols = symbols
        self.current_candles = {}
        self.last_minute = {}

    def update_tick(self, symbol, tick_data):
        """
        tick_data expected format:
        {
            "LTP": float,
            "Volume": int
        }
        """

        now = dt.datetime.now().replace(second=0, microsecond=0)

        price = tick_data["LTP"]
        volume = tick_data["Volume"]

        # Initialize if new minute
        if symbol not in self.current_candles:
            self._start_new_candle(symbol, now, price, volume)
            return None

        # If minute changed → finalize previous candle
        if now != self.last_minute[symbol]:
            finished = self.current_candles[symbol]

            self._start_new_candle(symbol, now, price, volume)

            return finished

        # Update existing candle
        candle = self.current_candles[symbol]
        candle["high"] = max(candle["high"], price)
        candle["low"] = min(candle["low"], price)
        candle["close"] = price
        candle["volume"] += volume

        return None

    def _start_new_candle(self, symbol, minute, price, volume):
        self.last_minute[symbol] = minute

        self.current_candles[symbol] = {
            "date": minute,
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "volume": volume
        }