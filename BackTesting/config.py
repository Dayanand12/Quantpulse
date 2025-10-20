# config.py
# Time Window
opening_start = '09:15'
opening_end = '09:30'
exit_time = '15:15'  # Time to close all trades (EOD exit)

# Symbols
symbol = 'BANKNIFTY23APR-FUT'
option_symbol = 'BANKNIFTY23APR45000CE'

# Trade Settings
order_qty = 15
max_trades = 3

# Risk Management
risk_per_trade = 1000  # INR
reward_to_risk = 2.0   # Reward:Risk ratio (e.g., 1:2)
trailing_trigger_rr = 1.2  # Start trailing after reaching 1.2R