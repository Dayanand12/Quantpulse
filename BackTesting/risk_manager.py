from config import max_trades
from logger import log_event, log_structured

trade_count = 0
current_balance = 100000
profit_loss = 0

def can_trade():
    global trade_count
    return trade_count < max_trades

def register_trade():
    global trade_count
    trade_count += 1

def update_pnl(profit, trade_time=None, entry_price=None, latest_vwap=None):
    global current_balance, profit_loss, trade_count
    profit_loss += profit
    current_balance += profit
    log_event(f"Profit/Loss updated: {profit}, Current Balance: {current_balance}")
    if trade_time:
        log_structured(
            trade_time=trade_time,
            action="BUY",
            entry_price=entry_price,
            vwap=latest_vwap,
            profit=profit,
            balance=current_balance,
            trade_no=trade_count
        )

def get_balance():
    return current_balance

def get_pnl():
    return profit_loss