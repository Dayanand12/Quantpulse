# core/domain/regime_snapshot.py
"""Structured, multi-dimensional regime classification captured at trade
entry — extends core/domain/market_condition.py's single squashed string
("Trending / High Volume / Above VWAP") with independently filterable/
sortable dimensions, so a report can slice "win rate when regime_trend=
Bullish Trend AND vix_bucket=Low" instead of only matching an exact
composite label (which fragments sample size fast).

Reuses classify_regime() (core/domain/regime_classification.py) rather
than re-deriving trend/volatility logic here, so a Trade's regime_trend
can never disagree with what the Market Analysis page would have called
that same symbol at that same moment.

Pure and framework-agnostic: every input is a value the caller already
computed (the live per-symbol indicator snapshot — runners/paper_trading/
live_engine.py — or the backtest snapshot series — runners/backtesting/
snapshot_builder.py/engine.py). Nothing here fetches or recomputes an
indicator itself, and every dimension is independently None-safe: a
symbol this account doesn't track (e.g. INDIA VIX dropped from the
watchlist) degrades that one column to None rather than failing the
whole trade.
"""

from datetime import datetime, time
from typing import Optional, TypedDict

from core.domain.regime_classification import classify_regime

# India VIX absolute level buckets — the standard first-look "which
# playbook applies today" dial professional desks check before leaning
# trend-following vs mean-reversion: low VIX days tend to reward trend/
# breakout entries, high VIX days tend to chop trend systems and reward
# faster mean-reversion exits. Rough NSE convention (sub-13 = complacent/
# low-vol, 13-18 = normal, 18+ = elevated fear/high-vol) — tune if this
# account's own history disagrees once there's enough logged data to tell.
VIX_LOW_THRESHOLD = 13.0
VIX_HIGH_THRESHOLD = 18.0

# Intraday session phases — cheap to compute, and an edge that holds at
# 9:20 often behaves differently by 14:30 (opening-range volatility fades,
# lunch-hour chop, closing-hour positioning), so this is worth splitting
# out even before any of the other dimensions are wired up.
_OPENING_END = time(9, 45)
_CLOSING_START = time(14, 0)


class RegimeFields(TypedDict):
    regime_trend: Optional[str]
    regime_volatility: Optional[str]
    index_trend: Optional[str]
    vix_bucket: Optional[str]
    session_phase: Optional[str]


def _vix_bucket(vix_ltp: Optional[float]) -> Optional[str]:
    if vix_ltp is None:
        return None
    if vix_ltp < VIX_LOW_THRESHOLD:
        return "Low"
    if vix_ltp > VIX_HIGH_THRESHOLD:
        return "High"
    return "Medium"


def _session_phase(entry_time: Optional[datetime]) -> Optional[str]:
    if entry_time is None:
        return None
    t = entry_time.time()
    if t < _OPENING_END:
        return "Opening"
    if t >= _CLOSING_START:
        return "Closing"
    return "Mid-day"


def build_regime_fields(snapshot: dict, entry_time: Optional[datetime]) -> RegimeFields:
    """snapshot: the entry-time raw indicator dict already captured at
    entry (the traded symbol's own ltp/ema9/ema21/adx/vwap/atr_pct, plus
    nifty_ltp/nifty_ema9/nifty_ema21/nifty_adx/nifty_vwap/nifty_atr_pct and
    vix_ltp where those symbols are tracked — see
    runners/paper_trading/execution_manager.py::_manage_entries and
    runners/backtesting/engine.py's NIFTY/VIX regime joins). entry_time:
    the position's own entry timestamp (Trade.opened_at), not the bar this
    is evaluated from — regime is a property of when the trade was taken,
    not of whenever this function happens to run.
    """
    own_inputs = (
        snapshot.get("ltp"), snapshot.get("ema9"), snapshot.get("ema21"),
        snapshot.get("adx"), snapshot.get("vwap"), snapshot.get("atr_pct"),
    )
    own = classify_regime(*own_inputs) if all(v is not None for v in own_inputs) else None

    index_inputs = (
        snapshot.get("nifty_ltp"), snapshot.get("nifty_ema9"), snapshot.get("nifty_ema21"),
        snapshot.get("nifty_adx"), snapshot.get("nifty_vwap"), snapshot.get("nifty_atr_pct"),
    )
    index = classify_regime(*index_inputs) if all(v is not None for v in index_inputs) else None

    return {
        "regime_trend": own["regime"] if own else None,
        "regime_volatility": own["volatility_state"] if own else None,
        "index_trend": index["regime"] if index else None,
        "vix_bucket": _vix_bucket(snapshot.get("vix_ltp")),
        "session_phase": _session_phase(entry_time),
    }
