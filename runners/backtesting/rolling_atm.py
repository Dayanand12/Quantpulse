# runners/backtesting/rolling_atm.py
"""A realistic alternative to chain-sweep's "which historical contract
would have worked best" (a fundamentally hindsight question, useful for
finding patterns but not directly tradeable — the exact contract that
looked best won't exist next month): this rolls through an underlying's
expiries IN ORDER and, at each roll point, picks whichever CE/PE strike
is closest to spot AT THAT MOMENT — the same information a real trader
would actually have. Held to expiry, then re-selected (not re-picked on a
fixed schedule) — see this project's Phase 4 scope decision.

Each period is an independent single-contract backtest (fresh strategy
instance, that contract's own OHLC — same run_backtest() call chain-sweep
already uses for one contract), so there's no cross-contract indicator
continuity problem the way stitching a synthetic continuous price series
would have (a new ATM contract's premium isn't a continuation of the old
one's, the way a rolled futures price roughly is). The periods' trade
lists are just concatenated afterward — trades are discrete events, so
concatenation has none of a raw-price-series roll's discontinuity issues.
"""

import datetime as dt
import os
from typing import Any, Dict, List, Optional, Tuple, Type

import polars as pl

from core.application.interfaces.strategy import IStrategy
from core.domain.charges import ChargeConfig
from core.domain.models import OptionContract, StrategyConfig, Trade
from runners.backtesting.engine import run_backtest
from runners.backtesting.historical_loader import (
    list_option_contracts,
    load_backtest_csv,
    load_equity_csv,
    option_csv_path,
)

# Option contracts for these underlyings are named "NIFTY"/"BANKNIFTY" (see
# Data_ingestion/options_ingest_index.py), but the trusted equity spot CSV
# these underlyings actually need is named after Kite's own index
# tradingsymbol -- resolved here once rather than left for every caller to
# rediscover.
_INDEX_SPOT_NAME = {"NIFTY": "NIFTY 50", "BANKNIFTY": "NIFTY BANK"}


def _spot_csv_path(underlying: str, historical_data_dir: str) -> str:
    name = _INDEX_SPOT_NAME.get(underlying, underlying)
    return os.path.join(historical_data_dir, f"{name}_historical.csv")


class RollEvent:
    def __init__(self, expiry: str, symbol: Optional[str], strike: Optional[float], spot_at_roll: Optional[float], note: str = ""):
        self.expiry = expiry
        self.symbol = symbol
        self.strike = strike
        self.spot_at_roll = spot_at_roll
        self.note = note

    def to_dict(self) -> Dict[str, Any]:
        return {
            "expiry": self.expiry,
            "symbol": self.symbol,
            "strike": self.strike,
            "spot_at_roll": self.spot_at_roll,
            "note": self.note,
        }


def _closest_strike_contract(contracts: List[OptionContract], spot: float) -> OptionContract:
    return min(contracts, key=lambda c: abs(c.strike - spot))


def run_rolling_atm_backtest(
    strategy_cls: Type[IStrategy],
    underlying: str,
    category: str,
    side: str,
    config: StrategyConfig,
    historical_data_dir: str,
    charge_config: Optional[ChargeConfig] = None,
    date_from: Optional[dt.date] = None,
    date_to: Optional[dt.date] = None,
    extra_indicators: Optional[list] = None,
) -> Tuple[List[Trade], List[RollEvent]]:
    """Held-to-expiry rolling ATM backtest for one underlying+side. Returns
    (all trades across every period concatenated in time order, a log of
    which contract got picked at each roll and why) — the roll log is
    what makes this auditable instead of a black box: every strike choice
    traces back to a real spot price observed at a real prior date, never
    the contract's own future performance.
    """
    # Spot is plain equity/index OHLCV, not an option file — load_equity_csv
    # directly (load_backtest_csv would reach the same place via its
    # oi-column auto-detect, but this is unambiguous and skips the header
    # peek).
    spot_path = _spot_csv_path(underlying, historical_data_dir)
    spot_df = load_equity_csv(spot_path)

    expiries = sorted(
        c.expiry for c in list_option_contracts(underlying, category, historical_data_dir)
    )
    # One entry per distinct expiry, sorted — list_option_contracts returns
    # one row per contract (many strikes per expiry), so dedupe first.
    seen = set()
    ordered_expiries = []
    for e in expiries:
        if e not in seen:
            seen.add(e)
            ordered_expiries.append(e)

    if date_from or date_to:
        ordered_expiries = [
            e for e in ordered_expiries
            if (date_from is None or e >= date_from) and (date_to is None or e <= date_to)
        ]

    all_trades: List[Trade] = []
    roll_log: List[RollEvent] = []
    prior_expiry: Optional[dt.date] = None

    for expiry in ordered_expiries:
        contracts_this_expiry = [
            c for c in list_option_contracts(underlying, category, historical_data_dir, expiry=expiry.isoformat())
            if c.side == side
        ]
        if not contracts_this_expiry:
            roll_log.append(RollEvent(expiry.isoformat(), None, None, None, "no contracts for this side/expiry"))
            continue

        # Spot as of the roll point: the prior expiry's close (the last
        # date we'd actually have known, with no look-ahead). For the
        # very first period there's no prior roll — 30 days before THIS
        # expiry approximates "just after this contract was listed"
        # (monthly contracts list roughly a month out). Verified this
        # matters: using the spot history's absolute earliest date
        # instead (spot_df["date"].min()) picked up RELIANCE's ~2015
        # pre-split price of 214 for a 2024 expiry, versus every other
        # roll correctly landing in the 1200-1500 range.
        reference_date = prior_expiry if prior_expiry is not None else expiry - dt.timedelta(days=30)
        candidates = spot_df.filter(pl.col("date").dt.date() <= reference_date)
        if candidates.height == 0:
            roll_log.append(RollEvent(expiry.isoformat(), None, None, None, "no spot data at/before roll point"))
            prior_expiry = expiry
            continue
        spot_at_roll = candidates.sort("date")["close"][-1]

        contract = _closest_strike_contract(contracts_this_expiry, spot_at_roll)
        csv_path = option_csv_path(contract, category, historical_data_dir)
        try:
            df = load_backtest_csv(csv_path)
        except Exception as e:  # noqa: BLE001 -- one bad period must not kill the whole roll
            roll_log.append(RollEvent(expiry.isoformat(), contract.symbol, contract.strike, spot_at_roll, f"error: {e}"))
            prior_expiry = expiry
            continue

        strategy_instance = strategy_cls()
        trades = run_backtest(
            strategy_instance, contract.symbol, df, config, charge_config=charge_config,
            date_from=date_from, date_to=date_to, extra_indicators=extra_indicators,
        )
        all_trades.extend(trades)
        roll_log.append(RollEvent(expiry.isoformat(), contract.symbol, contract.strike, spot_at_roll))
        prior_expiry = expiry

    all_trades.sort(key=lambda t: t.closed_at)
    return all_trades, roll_log
