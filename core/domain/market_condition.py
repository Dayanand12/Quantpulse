"""Classifies the market condition a trade was entered into, from the
same indicator snapshot IStrategy.screen() sees (see
core/application/interfaces/strategy.py). Pure and framework-agnostic —
called from infrastructure/trading/mappers.py::trade_from_raw() at the
point a closed trade's raw entry-time snapshot is turned into a Trade.

Exists so trades can be researched after the fact ("which strategy wins
in which condition") without recomputing indicators from scratch — the
label is denormalized onto Trade at close time, using whatever the
strategy itself saw at entry.
"""

from typing import Optional, Tuple

TRENDING_ADX_THRESHOLD = 25.0
HIGH_VOLUME_RATIO_THRESHOLD = 1.5


def classify_market_condition(
    ltp: Optional[float],
    adx: Optional[float],
    vwap: Optional[float],
    volume_ratio: Optional[float],
) -> Optional[str]:
    """None if the inputs needed to classify at all (adx, volume_ratio)
    are missing — e.g. trades logged before this field existed."""
    if adx is None or volume_ratio is None:
        return None

    parts = [
        "Trending" if adx >= TRENDING_ADX_THRESHOLD else "Ranging",
        "High Volume" if volume_ratio >= HIGH_VOLUME_RATIO_THRESHOLD else "Normal Volume",
    ]

    if ltp is not None and vwap is not None:
        parts.append("Above VWAP" if ltp >= vwap else "Below VWAP")

    return " / ".join(parts)


def split_market_condition(
    label: Optional[str],
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Inverse of the " / "-join above — for reports that want Trend/
    Volume/VWAP as independently sortable columns instead of one combined
    string (e.g. so "sort by Trend, then Win Rate" is possible in a
    spreadsheet without parsing the label by hand). (None, None, None) for
    a trade with no recorded condition."""
    if not label:
        return None, None, None
    parts = label.split(" / ")
    trend = parts[0] if len(parts) > 0 else None
    volume = parts[1] if len(parts) > 1 else None
    vwap = parts[2] if len(parts) > 2 else None
    return trend, volume, vwap
