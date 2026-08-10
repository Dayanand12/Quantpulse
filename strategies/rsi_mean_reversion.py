"""RSI Oversold Bounce (Long) — Larry Connors-style mean-reversion.

Classic proven intraday approach: don't fight the primary trend, but buy
sharp, short-term pullbacks within it. Requires price above ema21 (the
uptrend filter) AND RSI14 dipping into oversold territory (<=30) and
then turning back up — the pullback-is-over signal — rather than
buying the falling knife the moment RSI crosses below 30. Exit is
handled entirely by the universal SL/target/trailing machinery in
runners/paper_trading/execution_manager.py, same as every other
strategy — nothing here decides when to exit.

The actual threshold/conditions (oversold_rsi, the uptrend filter, the
RSI-turning-up crossing) live in rsi_mean_reversion.json next to this
file, not here — see core/domain/strategy_conditions.py. Edit that JSON
to tune this strategy; nothing in this .py file needs to change for a
threshold tweak.
"""

from core.domain.enums import OrderSide
from core.domain.json_condition_strategy import JsonConditionStrategy


class RsiMeanReversionStrategy(JsonConditionStrategy):
    name = "rsi_mean_reversion"
    display_name = "RSI Oversold Bounce (Long)"
    side = OrderSide.BUY
