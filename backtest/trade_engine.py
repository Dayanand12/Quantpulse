import polars as pl

class TradeEngine:
    def __init__(self, df, config):
        self.df = df
        self.config = config
        self.position = None
        self.entry_price = 0
        self.stop_loss = 0
        self.target = 0
        self.trail_price = 0
        self.trades_today = 0
        self.capital_used = 0

    def generate_signals(self, buy_mask, sell_mask):
        signals, entry_price, exit_price, stop_loss_list, target_list, exit_signals = [], [], [], [], [],[]

        current_day = None
        for i, row in enumerate(self.df.iter_rows(named=True)):
            day = row["date"].date()
            close = row["close"]
            high = row["high"]
            low = row["low"]

            if day != current_day:
                current_day = day
                self.trades_today = 0

            sig = None
            exit_sig = None

            # --- ENTRY LOGIC ---
            if self.position is None and self.trades_today < self.config["max_cycles_per_day"]:
                if sell_mask[i] and (self.capital_used + self.config["quantity"] * close <= self.config["max_capital"]):
                    sig = "SELL"
                    self.position = "SELL"
                    self.entry_price = close
                    self.stop_loss = close * (1 + self.config["stoploss_pct"] / 100)
                    self.target = close * (1 - self.config["target_pct"] / 100)
                    self.trail_price = close
                    self.trades_today += 1
                    self.capital_used += close * self.config["quantity"]

            # --- EXIT LOGIC ---
            if self.position == "SELL":
                # Stop-loss hit
                if high >= self.stop_loss:
                    exit_sig = "EXIT_SELL_SL"
                    self.position = None
                # Target hit
                elif low <= self.target:
                    exit_sig = "EXIT_SELL_TP"
                    self.position = None
                # Trailing stop
                else:
                    if close < self.trail_price * (1 - self.config["trailing_pct"] / 100):
                        exit_sig = "EXIT_SELL_TRAIL"
                        self.position = None
                    else:
                        self.trail_price = max(self.trail_price, close)

            signals.append(sig)
            entry_price.append(self.entry_price if sig else None)
            exit_price.append(close if exit_sig else None)
            exit_signals.append(exit_sig)
            stop_loss_list.append(self.stop_loss if self.position else None)
            target_list.append(self.target if self.position else None)

            if exit_sig:
                self.entry_price = 0
                self.stop_loss = 0
                self.target = 0
                self.trail_price = 0

        self.df = self.df.with_columns([
            pl.Series("Signal", signals),
            pl.Series("EntryPrice", entry_price),
            pl.Series("ExitPrice", exit_price),
            pl.Series("StopLoss", stop_loss_list),
            pl.Series("Target", target_list),
            pl.Series("ExitSignals", exit_signals)
        ])
        return self.df
