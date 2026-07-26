#engine.py
from live.live_engine import LiveEngine


class TradingEngine:
    def __init__(self):
        self.live_engine = None

    def start_live(self, symbols, capital=100000):
        self.live_engine = LiveEngine(symbols, capital)
        return self.live_engine

    def get_live_engine(self):
        return self.live_engine