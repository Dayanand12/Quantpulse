import datetime as dt

from core.domain.models import StrategyConfig
from runners.backtesting.parameter_sweep import build_config_grid, rank_by, sweep_parameters
from strategies.test_always_short import TestAlwaysShortStrategy

_FIRST_TRADEABLE_INDEX = 24


def _bar(day, index, open_, high, low, close, volume=1000.0):
    return {
        "date": dt.datetime.combine(day, dt.time(9, 15)) + dt.timedelta(minutes=index),
        "open": open_, "high": high, "low": low, "close": close, "volume": volume,
    }


def _write_sample_csv(path):
    day = dt.date(2026, 1, 5)
    rows = [_bar(day, i, 100.0, 100.0, 100.0, 100.0) for i in range(_FIRST_TRADEABLE_INDEX)]
    rows.append(_bar(day, _FIRST_TRADEABLE_INDEX, 100.0, 100.0, 100.0, 100.0))
    # High enough to blow through every stoploss_pct this test sweeps
    # (0.5% / 0.8% / 1.2% -> stop_loss 100.5 / 100.8 / 101.2), so every
    # config in the grid produces exactly one trade.
    rows.append(_bar(day, _FIRST_TRADEABLE_INDEX + 1, 100.0, 103.0, 99.5, 100.5))

    lines = ["date,open,high,low,close,volume"]
    for r in rows:
        lines.append(
            f"{r['date'].isoformat()}+05:30,{r['open']},{r['high']},{r['low']},{r['close']},{r['volume']}"
        )
    path.write_text("\n".join(lines))


def test_build_config_grid_produces_every_combination():
    grid = build_config_grid(
        StrategyConfig(), stoploss_pct=[0.5, 0.8], target_pct=[1.5, 2.0, 2.5]
    )

    assert len(grid) == 6
    pairs = {(c.stoploss_pct, c.target_pct) for c in grid}
    assert pairs == {
        (0.5, 1.5), (0.5, 2.0), (0.5, 2.5),
        (0.8, 1.5), (0.8, 2.0), (0.8, 2.5),
    }


def test_build_config_grid_with_no_ranges_returns_the_base_config():
    base = StrategyConfig()
    assert build_config_grid(base) == [base]


def test_sweep_parameters_runs_every_config_in_the_grid(tmp_path):
    csv_path = tmp_path / "SAMPLE_historical.csv"
    _write_sample_csv(csv_path)

    grid = build_config_grid(StrategyConfig(), stoploss_pct=[0.5, 0.8, 1.2])
    results = sweep_parameters(TestAlwaysShortStrategy, [("TEST", str(csv_path))], grid)

    assert len(results) == 3
    assert {r.config.stoploss_pct for r in results} == {0.5, 0.8, 1.2}
    assert all(r.metrics.total_trades == 1 for r in results)


def test_sweep_parameters_aggregates_multiple_symbols_per_config(tmp_path):
    csv_a = tmp_path / "A_historical.csv"
    csv_b = tmp_path / "B_historical.csv"
    _write_sample_csv(csv_a)
    _write_sample_csv(csv_b)

    grid = build_config_grid(StrategyConfig(), stoploss_pct=[0.5, 0.8])
    results = sweep_parameters(
        TestAlwaysShortStrategy, [("A", str(csv_a)), ("B", str(csv_b))], grid
    )

    assert len(results) == 2  # one per config, not per (symbol, config)
    assert all(r.metrics.total_trades == 2 for r in results)  # 1 trade each from A and B


def test_rank_by_sorts_none_last_regardless_of_direction():
    grid = build_config_grid(StrategyConfig(), stoploss_pct=[0.5])
    # Build fake results directly rather than running a real sweep, so the
    # None case (no losing trades yet -> profit_factor is None) is exact.
    from core.domain.metrics import compute_performance_metrics
    from runners.backtesting.parameter_sweep import SweepResult

    only_wins = compute_performance_metrics(
        [_win_trade()], capital=100_000
    )
    results = [SweepResult(config=grid[0], metrics=only_wins)]

    ranked_desc = rank_by(results, "profit_factor", reverse=True)
    ranked_asc = rank_by(results, "profit_factor", reverse=False)

    assert ranked_desc[0].metrics.profit_factor is None
    assert ranked_asc[0].metrics.profit_factor is None


def _win_trade():
    from core.domain.enums import OrderSide
    from core.domain.models import Trade

    return Trade(
        symbol="TEST", side=OrderSide.SELL, quantity=50,
        entry_price=100.0, exit_price=98.0, pnl=100.0,
        closed_at=dt.datetime(2026, 1, 5, 10, 0),
    )
