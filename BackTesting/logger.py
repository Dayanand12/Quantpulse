#logger.py
import datetime
log_file = "trade_log.txt"
structured_log_file = "structured_log.txt"

def get_daily_log_file():
    today_date = datetime.datetime.now().strftime("%Y-%m-%d")
    return f"trade_log_{today_date}.txt"

def log_event(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_file = get_daily_log_file()
    print(f"Logging to file: {log_file}")  # Debugging print
    with open(log_file, "a") as file:
        file.write(f"[{timestamp}] {message}\n")

def log_structured(trade_time, action, entry_price, vwap, profit, balance, trade_no):
    log_file = get_daily_log_file()
    print(f"Logging to structured file: {log_file}")  # Debugging print
    with open(log_file, "a") as file:
        file.write(
            f"Time: {trade_time} | Action: {action} | Entry: {entry_price} | VWAP: {vwap} | "
            f"Profit: {profit} | Current Balance: {balance} | Trade No: {trade_no}\n"
        )