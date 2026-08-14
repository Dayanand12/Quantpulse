import datetime as dt

import pytest

from backfill_per_symbol_results import backfill
from core.domain.backtest_result import BacktestRunParams
from infrastructure.config.settings import get_settings
from infrastructure.persistence.database import Base, create_session_factory
from infrastructure.persistence.sql_backtest_result_repository import SqlBacktestResultRepository
from runners.backtesting.result_persistence import symbols_identity


@pytest.fixture
def result_repo(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    get_settings.cache_clear()

    session_factory = create_session_factory(f"sqlite:///{db_path}")
    Base.metadata.create_all(session_factory().get_bind())
    yield SqlBacktestResultRepository(session_factory)

    get_settings.cache_clear()


def _save_combined_result(result_repo, strategy_name, by_symbol_metrics):
    """by_symbol_metrics: {symbol: total_trades} — builds a combined row
    shaped like what save_per_symbol_results's predecessor used to save,
    with a real by_symbol breakdown (the thing the backfill reads)."""
    by_symbol = [
        {
            "strategy_name": symbol,
            "deployment_id": None,
            "capital": 0,
            "metrics": {"total_trades": trades, "win_rate": None, "profit_factor": None},
        }
        for symbol, trades in by_symbol_metrics.items()
    ]
    params = BacktestRunParams(
        strategy_name=strategy_name,
        symbols=symbols_identity(list(by_symbol_metrics.keys()), is_full_watchlist=False),
        timeframe="minute", date_from=dt.date(2025, 1, 1), date_to=dt.date(2025, 12, 31),
        quantity=50, stoploss_pct=0.8, target_pct=2.0, trailing_pct=0.1, max_cycles_per_day=10,
        start_time="09:20", end_time="11:30", charges_enabled=True,
    )
    return result_repo.save_result(params, {
        "by_symbol": by_symbol, "capital": 100_000, "total_trades": sum(by_symbol_metrics.values()),
    })


def test_backfill_creates_one_row_per_symbol_from_combined_result(result_repo):
    _save_combined_result(result_repo, "my_strategy", {"RELIANCE": 5, "TCS": 3})

    backfill(strategy_name="my_strategy")

    all_results = result_repo.list_results("my_strategy")
    by_symbols_field = {r.params.symbols: r for r in all_results}
    assert "RELIANCE" in by_symbols_field
    assert "TCS" in by_symbols_field
    assert by_symbols_field["RELIANCE"].result["metrics"]["total_trades"] == 5
    assert by_symbols_field["TCS"].result["metrics"]["total_trades"] == 3
    # Original combined row is untouched, not deleted.
    assert "RELIANCE,TCS" in by_symbols_field


def test_backfill_is_idempotent(result_repo):
    _save_combined_result(result_repo, "my_strategy", {"RELIANCE": 5})

    backfill(strategy_name="my_strategy")
    after_first = {r.params.symbols: r.id for r in result_repo.list_results("my_strategy")}
    backfill(strategy_name="my_strategy")
    after_second = {r.params.symbols: r.id for r in result_repo.list_results("my_strategy")}

    # Same rows upserted in place, not duplicated on a second run.
    assert after_first == after_second


def test_backfill_dry_run_writes_nothing(result_repo):
    _save_combined_result(result_repo, "my_strategy", {"RELIANCE": 5, "TCS": 3})

    backfill(strategy_name="my_strategy", dry_run=True)

    all_results = result_repo.list_results("my_strategy")
    assert len(all_results) == 1  # only the original combined row


def test_backfill_skips_results_with_no_by_symbol_data(result_repo):
    # A --sweep-saved result has no by_symbol data to split — must not crash.
    params = BacktestRunParams(
        strategy_name="my_strategy", symbols="WATCHLIST", timeframe="minute",
        date_from=dt.date(2025, 1, 1), date_to=dt.date(2025, 12, 31),
        quantity=50, stoploss_pct=0.8, target_pct=2.0, trailing_pct=0.1, max_cycles_per_day=10,
        start_time="09:20", end_time="11:30", charges_enabled=True,
    )
    result_repo.save_result(params, {"by_symbol": [], "capital": 100_000})

    backfill(strategy_name="my_strategy")  # should not raise

    assert len(result_repo.list_results("my_strategy")) == 1


def test_backfill_without_strategy_argument_covers_every_strategy(result_repo):
    _save_combined_result(result_repo, "strategy_a", {"RELIANCE": 5})
    _save_combined_result(result_repo, "strategy_b", {"TCS": 2})

    backfill()  # no --strategy filter

    assert any(r.params.symbols == "RELIANCE" for r in result_repo.list_results("strategy_a"))
    assert any(r.params.symbols == "TCS" for r in result_repo.list_results("strategy_b"))
