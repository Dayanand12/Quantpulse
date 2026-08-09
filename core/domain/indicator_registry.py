# core/domain/indicator_registry.py
"""Registry of indicator TYPES (ema, rsi, adx, atr, ...) — the modular
replacement for runners/backtesting/snapshot_builder.py and
runners/paper_trading/live_engine.py each hardcoding "always compute
EMA5/9/21, RSI14, ADX14, ATR14" under fixed names.

Adding a new indicator type later is: write one function shaped
(df: pl.DataFrame, **params) -> pl.Series, register it in _REGISTRY below
— nothing in the pipeline that CALLS this registry needs to change. Wraps
indicators.py::IndicatorCalculator's existing (already-parameterized)
functions; this module doesn't reimplement any math.

This is ADDITIVE, not a replacement: the existing fixed snapshot fields
(ltp, ema5, ema9, ema21, rsi, adx, atr_pct, vwap, volume_ratio, orb_low,
distance_to_or_low — see core/domain/strategy_conditions.py::
VALID_SNAPSHOT_FIELDS) keep being computed exactly as before, for
orb_reversal/filter_engine.py and every strategy already using bare
field-name references. A strategy opts into a DYNAMIC indicator (any
period, not just the defaults) by declaring
{"indicator": "ema", "params": {"period": 20}} in its conditions.json
instead of a bare field name.
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Tuple

import polars as pl

from indicators import IndicatorCalculator


@dataclass(frozen=True)
class IndicatorSpec:
    """One concrete "compute this indicator with these params" request —
    e.g. IndicatorSpec.of("ema", period=20). `params` is stored as sorted
    (name, value) pairs so two specs built from differently-ordered dicts
    are still equal/hashable the same way — needed for compute_all()'s
    dedup."""

    type: str
    params: Tuple[Tuple[str, Any], ...]

    @staticmethod
    def of(indicator_type: str, **params: Any) -> "IndicatorSpec":
        return IndicatorSpec(indicator_type, tuple(sorted(params.items())))

    @property
    def params_dict(self) -> Dict[str, Any]:
        return dict(self.params)

    @property
    def key(self) -> str:
        """Canonical snapshot dict/column key — e.g. ema period=20 ->
        "ema_20". No params -> just the type name."""
        if not self.params:
            return self.type
        suffix = "_".join(str(v) for _, v in self.params)
        return f"{self.type}_{suffix}"


def _ema(df: pl.DataFrame, period: int = 9) -> pl.Series:
    return IndicatorCalculator.ema(df, period=period)


def _rsi(df: pl.DataFrame, period: int = 14) -> pl.Series:
    return IndicatorCalculator.rsi(df, period=period)


def _adx(df: pl.DataFrame, period: int = 14) -> pl.Series:
    return IndicatorCalculator.adx(df, period=period)


def _atr(df: pl.DataFrame, period: int = 14) -> pl.Series:
    return IndicatorCalculator.atr(df, period=period)


_REGISTRY: Dict[str, Callable[..., pl.Series]] = {
    "ema": _ema,
    "rsi": _rsi,
    "adx": _adx,
    "atr": _atr,
}


def available_indicator_types() -> List[str]:
    return sorted(_REGISTRY)


def compute(spec: IndicatorSpec, df: pl.DataFrame) -> pl.Series:
    """Computes one indicator over the FULL df (same "compute over full
    history, not incrementally" convention every indicator in this
    codebase already follows) and names the resulting Series spec.key —
    ready to .with_columns() straight onto a snapshot dataframe."""
    if spec.type not in _REGISTRY:
        raise ValueError(
            f"Unknown indicator type: {spec.type!r}. Available: {', '.join(available_indicator_types())}"
        )
    return _REGISTRY[spec.type](df, **spec.params_dict).rename(spec.key)


def compute_all(specs: List[IndicatorSpec], df: pl.DataFrame) -> pl.DataFrame:
    """Computes every distinct spec (deduplicated by .key, so two
    strategies both wanting ema period=20 only pay for it once) and
    returns them as extra columns on `df` — the caller decides how to
    fold that into whatever snapshot shape it's building."""
    seen: Dict[str, IndicatorSpec] = {}
    for spec in specs:
        seen.setdefault(spec.key, spec)

    if not seen:
        return df

    return df.with_columns([compute(spec, df) for spec in seen.values()])
