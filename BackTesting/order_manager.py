# order_manager.py

from broker_api import place_order
from config import option_symbol, order_qty, risk_per_trade, reward_to_risk, trailing_trigger_rr, exit_time
from indicators import calculate_vwap
from logger import log_event

# Trade state
trade_state = {
    'active': False,
    'entry_price': None,
    'stoploss_price': None,
    'target_price': None,
    'trailing_active': False
}

def execute_buy(entry_price):
    place_order(symbol=option_symbol, qty=order_qty, order_type='BUY')
    log_event(f"BUY Order placed for {option_symbol}, Qty: {order_qty}")
    print("BUY Order Placed")
    stoploss_points = risk_per_trade / order_qty
    stoploss_price = entry_price - stoploss_points
    target_price = entry_price + reward_to_risk * stoploss_points
    trade_state.update({
        'active': True,
        'entry_price': entry_price,
        'stoploss_price': stoploss_price,
        'target_price': target_price,
        'trailing_active': False
    })

def execute_exit(reason, price):
    place_order(symbol=option_symbol, qty=order_qty, order_type='SELL')
    log_event(f"SELL Order placed for {option_symbol}, Qty: {order_qty} | Reason: {reason} | Exit Price: {price}")
    print(f"SELL Order Placed - Reason: {reason}")
    entry_price = trade_state['entry_price']
    pnl = (price - entry_price) * order_qty
    trade_time = pd.Timestamp.now()
    update_pnl(pnl, trade_time=trade_time, entry_price=entry_price, latest_vwap=None)
    reset_trade_state()

def reset_trade_state():
    trade_state.update({
        'active': False,
        'entry_price': None,
        'stoploss_price': None,
        'target_price': None,
        'trailing_active': False
    })

def is_trade_active():
    return trade_state['active']

def check_exit_conditions(tick, data):
    if not trade_state['active']:
        return
    current_price = tick['last_price']
    timestamp = tick['timestamp']
    if current_price <= trade_state['stoploss_price']:
        execute_exit(reason="Stop-loss hit", price=current_price)
        return
    if current_price >= trade_state['target_price'] and not trade_state['trailing_active']:
        trade_state['trailing_active'] = True
        log_event(f"Target reached at {current_price}, trailing SL activated.")
    if trade_state['trailing_active']:
        data['vwap'] = calculate_vwap(data)
        if not data['vwap'].empty:
            trailing_sl = data['vwap'].iloc[-1]
            if current_price < trailing_sl:
                execute_exit(reason="Trailing SL (VWAP) hit", price=current_price)
                return
    if timestamp.strftime('%H:%M') >= exit_time:
        execute_exit(reason="Time-based exit", price=current_price)