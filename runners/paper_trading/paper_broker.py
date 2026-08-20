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
        # Every symbol gets its own fresh initial_capital-sized allocation
        # (e.g. 3L), independent of how many other positions this
        # deployment already has open — sized against initial_capital, NOT
        # the shared available_capital pool, which would otherwise drain
        # after the first couple of entries and starve every symbol
        # evaluated afterward in the same pass. See enter().
        return price > 0 and price <= self.initial_capital

    def enter(self, symbol, side, price, quantity, market_snapshot=None):
        required = price * quantity

        if required > self.initial_capital:
            if not self.can_enter(symbol, price, quantity):
                self.rejected_entries[symbol] = {
                    "symbol": symbol,
                    "side": side,
                    "quantity": quantity,
                    "price": price,
                    "required_capital": required,
                    "available_capital": self.initial_capital,
                    "reason": "insufficient_capital",
                    "at": datetime.now(),
                }
                print(f"❌ Not enough capital for even 1 share of {symbol}")
                return False

            # Fixed quantity doesn't fit the per-trade capital budget —
            # auto-downsize to the largest quantity that does (e.g.
            # capital=299,097 @ price=1,503 -> 199 shares) instead of
            # rejecting the entry outright.
            quantity = int(self.initial_capital // price)
            required = price * quantity

        self.rejected_entries.pop(symbol, None)
        self.available_capital -= required

        self.positions[symbol] = {
            "side": side,
            "qty": quantity,
            "entry": price,
            "entered_at": datetime.now(),
            # The strategy's own indicator snapshot at entry (ltp, rsi,
            # adx, vwap, volume_ratio, ...) — carried through to exit()'s
            # trade_log entry purely for after-the-fact research; never
            # read by any entry/exit decision. Copied so a caller mutating
            # its snapshot dict on later ticks can't retroactively change
            # what this position remembers about its own entry.
            "market_snapshot": dict(market_snapshot) if market_snapshot is not None else None,
        }

        print(f"✅ ENTER {side} {symbol} @ {price} qty={quantity}")
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
            # None for a position opened before this field existed (still
            # open in memory when this code was deployed) — see
            # trade_from_raw's guard.
            "opened_at": pos.get("entered_at"),
            "closed_at": datetime.now(),
            "market_snapshot": pos.get("market_snapshot"),
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