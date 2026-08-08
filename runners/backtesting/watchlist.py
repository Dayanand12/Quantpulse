# runners/backtesting/watchlist.py
"""Reads the live watchlist for backtesting purposes — shared by
run_backtest.py (CLI) and backtest_server.py (API) so "the whole
watchlist" means the same set of symbols in both.
"""

from typing import List

from infrastructure.config.settings import get_settings
from infrastructure.persistence.database import create_session_factory
from infrastructure.persistence.sql_watchlist_repository import SqlWatchlistRepository

# Index symbols sit in the watchlist for the live ticker display (see
# infrastructure/config/settings.py::market_ticker_symbols) but aren't
# tradeable the way an equity is — no deployment ever screens them, and
# Data_ingestion's historical fetch doesn't cover them the same way.
NON_TRADEABLE_WATCHLIST_SYMBOLS = {"NIFTY 50", "NIFTY BANK", "INDIA VIX"}


def get_tradeable_watchlist_symbols() -> List[str]:
    settings = get_settings()
    session_factory = create_session_factory(settings.database_url)
    symbols = SqlWatchlistRepository(session_factory).get_symbols()
    return [s for s in symbols if s not in NON_TRADEABLE_WATCHLIST_SYMBOLS]
