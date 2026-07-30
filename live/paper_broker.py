# live/paper_broker.py

from datetime import datetime


class PaperBroker:
    def __init__(self, initial_capital=100000):
        self.initial_capital = initial_capital
        self.available_capital = initial_capital
        self.positions = {}   # {symbol: {side, qty, entry}}
        self.trade_log = []
        # symbol -> {symbol, side, quantity, price, required_capital,
        # available_capital, reason, at} — the most recent entry rejection
        # for a symbol, so "why hasn't this fired" is queryable instead of
        # only ever printed to the console. Cleared the moment that symbol
        # successfully enters, so a stale rejection from hours ago doesn't
        # linger after the underlying problem is fixed.
        self.rejected_entries = {}

    def can_enter(self, symbol, price, quantity):
        required = price * quantity
        return required <= self.available_capital

    def enter(self, symbol, side, price, quantity):
        required = price * quantity

        if not self.can_enter(symbol, price, quantity):
            self.rejected_entries[symbol] = {
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": price,
                "required_capital": required,
                "available_capital": self.available_capital,
                "reason": "insufficient_capital",
                "at": datetime.now(),
            }
            print(f"❌ Not enough capital for {symbol}")
            return False

        self.rejected_entries.pop(symbol, None)
        self.available_capital -= required

        self.positions[symbol] = {
            "side": side,
            "qty": quantity,
            "entry": price
        }

        print(f"✅ ENTER {side} {symbol} @ {price}")
        return True

    def exit(self, symbol, price, initial_stop_loss=None):
        if symbol not in self.positions:
            return

        pos = self.positions.pop(symbol)

        if pos["side"] == "SELL":
            pnl = (pos["entry"] - price) * pos["qty"]
        else:
            pnl = (price - pos["entry"]) * pos["qty"]

        released = pos["entry"] * pos["qty"]
        self.available_capital += released + pnl

        self.trade_log.append({
            "symbol": symbol,
            "entry": pos["entry"],
            "exit": price,
            "side": pos["side"],
            "qty": pos["qty"],
            "pnl": pnl,
            "initial_stop_loss": initial_stop_loss,
            "closed_at": datetime.now(),
        })

        print(f"🔁 EXIT {symbol} | PnL: {pnl}")

    def status(self):
        return {
            "available_capital": self.available_capital,
            "open_positions": self.positions,
            "total_trades": len(self.trade_log),
            "trade_log": self.trade_log,
            "rejected_entries": self.rejected_entries,
        }