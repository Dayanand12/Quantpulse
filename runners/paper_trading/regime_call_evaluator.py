"""Background thread that backfills forward returns on logged regime calls
(see services/market_analysis_engine.py's accuracy tracking) once enough
time has actually elapsed — 15/30/60 minutes after the call's candle
closed — so the rolling win-rate stat in the Decision panel has something
to compute against.

Batches one historical-candle fetch per symbol per run rather than one per
pending row, so a backlog of pending calls doesn't turn into a burst of
per-row Zerodha API calls.
"""

import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from core.application.interfaces.regime_call_repository import (
    Horizon,
    IRegimeCallRepository,
    PendingEvaluation,
)
from Data_ingestion.client import ZerodhaClient
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

_POLL_SECONDS = 120
_HORIZONS: tuple = ("15m", "30m", "60m")
_HORIZON_MINUTES: Dict[Horizon, int] = {"15m": 15, "30m": 30, "60m": 60}


def _naive(timestamp: datetime) -> datetime:
    """Historical candles come back tz-aware IST (see
    market_analysis_engine.py's docstring); regime_calls.logged_at is
    stored naive IST. Strip tzinfo so the two are directly comparable —
    both already represent the same IST wall-clock instant."""
    return timestamp.replace(tzinfo=None) if timestamp.tzinfo else timestamp


def _price_at_or_after(candles: List[dict], target: datetime) -> Optional[float]:
    for candle in candles:
        if _naive(candle["date"]) >= target:
            return candle["close"]
    return None


def _evaluate_horizon(
    horizon: Horizon,
    zerodha_client: ZerodhaClient,
    repository: IRegimeCallRepository,
) -> None:
    now = datetime.now()
    pending = repository.pending_evaluations(horizon, now)
    if not pending:
        return

    by_symbol: Dict[str, List[PendingEvaluation]] = {}
    for call in pending:
        by_symbol.setdefault(call.symbol, []).append(call)

    minutes = _HORIZON_MINUTES[horizon]

    for symbol, calls in by_symbol.items():
        earliest = min(c.logged_at for c in calls)
        try:
            candles = zerodha_client.fetch_historical_data(
                symbol=symbol,
                interval="minute",
                from_date=earliest,
                to_date=now,
                exchange=zerodha_client.exchange,
            )
        except Exception:
            logger.exception("Regime call evaluator: failed to fetch candles for %s", symbol)
            continue

        for call in calls:
            target = call.logged_at + timedelta(minutes=minutes)
            price = _price_at_or_after(candles, target)
            if price is None or not call.ltp:
                continue
            pct_return = (price - call.ltp) / call.ltp * 100
            repository.record_return(call.id, horizon, pct_return)


def run_regime_call_evaluator(
    zerodha_client: ZerodhaClient,
    repository: IRegimeCallRepository,
) -> None:
    """Blocks forever — run this in a daemon thread."""
    while True:
        for horizon in _HORIZONS:
            try:
                _evaluate_horizon(horizon, zerodha_client, repository)
            except Exception:
                logger.exception("Regime call evaluator failed for horizon %s", horizon)
        time.sleep(_POLL_SECONDS)
