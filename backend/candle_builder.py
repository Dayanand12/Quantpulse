import datetime as dt


class CandleBuilder:

    def __init__(self, symbols):
        self.current = {s: None for s in symbols}
        self.last_minute = {s: None for s in symbols}

    def process_tick(self, symbol, tick):

        price = tick.get("LTP")
        volume = tick.get("Volume", 0)

        now = dt.datetime.now().replace(second=0, microsecond=0)

        # first tick
        if self.current[symbol] is None:

            self.current[symbol] = {
                "date": now,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": volume
            }

            self.last_minute[symbol] = now
            return None

        candle = self.current[symbol]

        # update candle
        candle["high"] = max(candle["high"], price)
        candle["low"] = min(candle["low"], price)
        candle["close"] = price
        candle["volume"] += volume

        # minute changed → close candle
        if now != self.last_minute[symbol]:

            completed = candle.copy()

            self.current[symbol] = {
                "date": now,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": volume
            }

            self.last_minute[symbol] = now

            return completed

        return None