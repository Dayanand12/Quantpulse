from config import opening_start, opening_end
from data_handler import append_tick, get_data
from indicators import calculate_vwap
from order_manager import execute_buy, check_exit_conditions
from risk_manager import can_trade, register_trade, update_pnl
from logger import log_event
import pandas as pd

def on_tick(tick):
    append_tick(tick)
    data = get_data()
    current_time = tick['timestamp']
    if current_time.strftime('%H:%M:%S') >= opening_end + ':00':
        if not data.empty:
            first_date = data['timestamp'].iloc[0].date()
            start_datetime = pd.to_datetime(f"{first_date} {opening_start}:00")
            end_datetime = pd.to_datetime(f"{first_date} {opening_end}:00")
            opening_range = data[(data['timestamp'] >= start_datetime) & (data['timestamp'] <= end_datetime)]
            if not opening_range.empty:
                high = opening_range['high'].max()
                latest_close = data['close'].iloc[-1]
                data['vwap'] = calculate_vwap(data)
                if not data['vwap'].empty:
                    latest_vwap = data['vwap'].iloc[-1]
                    avg_vol = data['volume'].tail(5).mean()
                    if latest_close > high and latest_close > latest_vwap:
                        if not pd.isna(avg_vol) and tick['volume'] > 1.5 * avg_vol:
                            if can_trade():
                                execute_buy(entry_price=latest_close)
                                register_trade()
                                log_event(f"Trade executed at {current_time} | Close: {latest_close} | VWAP: {latest_vwap}")
                    else:
                        log_event(f"[{current_time}] No buy signal found (Close ≤ High or VWAP).")
                else:
                    log_event(f"[{current_time}] VWAP could not be calculated (insufficient data).")
            else:
                log_event(f"[{current_time}] Opening range data is empty.")
    check_exit_conditions(tick, data)