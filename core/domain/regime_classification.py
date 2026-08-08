"""Live regime classification — turns a point-in-time indicator reading
(ltp/ema9/ema21/adx/vwap/atr_pct) into a BUY/SELL-aware verdict, and turns
that same reading into the discrete "screens" the Screener page filters
on (Trending Up, Oversold, ...).

Pure and framework-agnostic, same spirit as metrics.py: no I/O. Used by
services/market_analysis_engine.py (one symbol, on-demand, backed by a
Kite history pull) and by server/main.py's live snapshot broadcast (every
watchlist symbol, every tick, backed by whatever's already in the
in-memory indicator cache) — both go through classify_regime() so the two
pages can never disagree about what "Bullish Trend" means.
"""

from typing import List, Optional, TypedDict


class RegimeClassification(TypedDict):
    regime: str
    trend_strength: str
    volatility_state: str
    confidence_score: int
    decision: str
    suggested_side: Optional[str]
    summary: str


def classify_regime(ltp, ema9, ema21, adx, vwap, atr_pct) -> RegimeClassification:
    """decision/suggested_side are BUY-or-SELL aware (not SELL-only like the
    original ORB-era heuristic): the app runs both BUY-side (EMA Crossover,
    VWAP Reclaim, RSI Mean Reversion) and SELL-side (ORB Reversal)
    strategies, so "what to do today" has to reflect whichever side the
    regime actually favors.

    Callers are expected to only pass real values here (see
    market_analysis_engine.analyze()'s _MIN_CANDLES gate, or
    server/main.py's None-check before calling this for a live snapshot
    row) — missing inputs are coerced to 0 rather than raising, which
    reads as a legitimate "Range / Weak / Compressed / NO TRADE" verdict
    if fed to a symbol that's actually just not warmed up yet.
    """
    ema9 = ema9 or 0
    ema21 = ema21 or 0
    adx = adx or 0
    vwap = vwap or 0
    atr_pct = atr_pct or 0

    if ema9 > ema21 and ltp > vwap:
        regime = "Bullish Trend"
    elif ema9 < ema21 and ltp < vwap:
        regime = "Bearish Trend"
    elif adx < 18:
        regime = "Range"
    else:
        regime = "Transition"

    if adx > 25:
        trend_strength = "Strong"
    elif adx > 20:
        trend_strength = "Moderate"
    else:
        trend_strength = "Weak"

    if atr_pct > 1.2:
        volatility_state = "High Expansion"
    elif atr_pct < 0.5:
        volatility_state = "Compressed"
    else:
        volatility_state = "Normal"

    score = 0
    if regime in ("Bullish Trend", "Bearish Trend"):
        score += 3
    elif regime == "Range":
        score += 2

    if trend_strength == "Strong":
        score += 2
    elif trend_strength == "Moderate":
        score += 1

    if volatility_state == "Normal":
        score += 2
    elif volatility_state == "Compressed":
        score += 1

    if volatility_state == "High Expansion" or score < 4 or regime not in (
        "Bullish Trend", "Bearish Trend"
    ):
        decision = "NO TRADE"
        suggested_side = None
    else:
        side = "BUY" if regime == "Bullish Trend" else "SELL"
        size = "NORMAL SIZE" if score >= 7 else "REDUCED SIZE"
        decision = f"{side} {size}"
        suggested_side = side

    return {
        "regime": regime,
        "trend_strength": trend_strength,
        "volatility_state": volatility_state,
        "confidence_score": score,
        "decision": decision,
        "suggested_side": suggested_side,
        "summary": _summary(regime, trend_strength, volatility_state, decision, suggested_side),
    }


def _summary(regime, trend_strength, volatility_state, decision, suggested_side) -> str:
    base = f"{trend_strength} {regime.lower()}, {volatility_state.lower()} volatility."

    if suggested_side is None:
        action = "Conditions don't favor either side right now — sit out or wait for a clearer setup."
    else:
        size = "full size" if "NORMAL" in decision else "reduced size"
        action = f"Favors {suggested_side}-side strategies today, at {size}."

    return f"{base} {action}"


# Screener category thresholds — deliberately looser than classify_regime's
# own decision gate (score >= 4, single best regime) since these are meant
# to build a browsing list ("worth a look today for any of my strategies"),
# not a go/no-go trade signal. A symbol can land in more than one screen.
OVERSOLD_RSI = 35.0
NEAR_VWAP_PCT = 0.3  # within this % of VWAP, either side
HIGH_VOL_VOLUME_RATIO = 1.5
HIGH_VOL_ATR_PCT = 1.0


def classify_screens(
    regime: Optional[RegimeClassification],
    *,
    ltp: Optional[float],
    vwap: Optional[float],
    rsi: Optional[float],
    volume_ratio: Optional[float],
    atr_pct: Optional[float],
) -> List[str]:
    """Which Screener categories a symbol belongs to right now. Each check
    is independently None-guarded so a symbol still warming up (missing
    ADX, say) can still show up under Oversold/High Volatility once RSI
    and volume_ratio are available, rather than waiting on every input.

    `regime` reuses classify_regime's own Bullish/Bearish Trend verdict
    for Trending Up/Down instead of re-deriving it here, so there's one
    place that decides what counts as trending."""
    screens: List[str] = []

    if regime is not None:
        if regime["regime"] == "Bullish Trend":
            screens.append("Trending Up")
        elif regime["regime"] == "Bearish Trend":
            screens.append("Trending Down")

    if ltp is not None and vwap:
        if abs(ltp - vwap) / vwap * 100 <= NEAR_VWAP_PCT:
            screens.append("Near VWAP")

    if rsi is not None and rsi <= OVERSOLD_RSI:
        screens.append("Oversold")

    if (volume_ratio is not None and volume_ratio >= HIGH_VOL_VOLUME_RATIO) or (
        atr_pct is not None and atr_pct >= HIGH_VOL_ATR_PCT
    ):
        screens.append("High Volatility")

    return screens
