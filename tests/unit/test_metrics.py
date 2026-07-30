import datetime as dt

import pytest

from core.domain.enums import OrderSide
from core.domain.metrics import (
    compute_performance_metrics,
    drawdown_series,
    equity_curve,
    pnl_by_period,
    profit_distribution,
    rolling_sharpe,
)
from core.domain.models import Trade


def make_trade(pnl, entry_price=100.0, initial_stop_loss=None, quantity=10, closed_at=None):
    return Trade(
        symbol="RELIANCE",
        side=OrderSide.SELL,
        quantity=quantity,
        entry_price=entry_price,
        exit_price=entry_price,  # not used by metrics; pnl is what matters
        pnl=pnl,
        closed_at=closed_at or dt.datetime(2026, 1, 1),
        initial_stop_loss=initial_stop_loss,
    )


def test_no_trades_returns_all_none_or_zero():
    metrics = compute_performance_metrics([], capital=100_000)

    assert metrics.total_trades == 0
    assert metrics.win_rate is None
    assert metrics.profit_factor is None
    assert metrics.max_drawdown == 0.0
    assert metrics.avg_r_multiple is None
    assert metrics.sharpe_ratio is None


def test_win_rate_and_profit_factor():
    trades = [make_trade(100), make_trade(-50), make_trade(80), make_trade(-120), make_trade(30)]

    metrics = compute_performance_metrics(trades, capital=100_000)

    assert metrics.total_trades == 5
    assert metrics.win_rate == 60.0
    assert metrics.gross_profit == 210
    assert metrics.gross_loss == -170
    assert metrics.profit_factor == pytest.approx(210 / 170)
    assert metrics.total_pnl == 40


def test_profit_factor_is_none_when_no_losses_yet():
    trades = [make_trade(100), make_trade(50)]

    metrics = compute_performance_metrics(trades, capital=100_000)

    assert metrics.profit_factor is None


def test_max_drawdown_from_known_equity_curve():
    # cumulative: 100, 50, 130, 10, 40 -> peak 100,100,130,130,130 -> dd 0,50,0,120,90
    trades = [make_trade(100), make_trade(-50), make_trade(80), make_trade(-120), make_trade(30)]

    metrics = compute_performance_metrics(trades, capital=100_000)

    assert metrics.max_drawdown == 120
    assert metrics.max_drawdown_pct == pytest.approx(0.12)  # 120 / 100_000 * 100


def test_max_drawdown_orders_trades_by_closed_at_not_input_order():
    # Same sequence as above but shuffled in the input list — result must
    # be identical since the function sorts by closed_at internally.
    day1 = dt.datetime(2026, 1, 1)
    trades_in_order = [
        make_trade(100, closed_at=day1 + dt.timedelta(minutes=0)),
        make_trade(-50, closed_at=day1 + dt.timedelta(minutes=1)),
        make_trade(80, closed_at=day1 + dt.timedelta(minutes=2)),
        make_trade(-120, closed_at=day1 + dt.timedelta(minutes=3)),
        make_trade(30, closed_at=day1 + dt.timedelta(minutes=4)),
    ]
    shuffled = [trades_in_order[3], trades_in_order[0], trades_in_order[4], trades_in_order[1], trades_in_order[2]]

    metrics = compute_performance_metrics(shuffled, capital=100_000)

    assert metrics.max_drawdown == 120


def test_avg_r_multiple_excludes_trades_without_initial_stop_loss():
    trades = [
        make_trade(50, entry_price=100.0, initial_stop_loss=102.0, quantity=10),  # risk=20, r=2.5
        make_trade(-25, entry_price=200.0, initial_stop_loss=190.0, quantity=5),  # risk=50, r=-0.5
        make_trade(999, entry_price=100.0, initial_stop_loss=None, quantity=10),  # excluded
    ]

    metrics = compute_performance_metrics(trades, capital=100_000)

    assert metrics.avg_r_multiple == pytest.approx(1.0)


def test_avg_r_multiple_is_none_when_no_trade_has_stop_loss():
    trades = [make_trade(100), make_trade(-50)]

    metrics = compute_performance_metrics(trades, capital=100_000)

    assert metrics.avg_r_multiple is None


def test_sharpe_ratio_is_none_with_fewer_than_two_trading_days():
    trades = [make_trade(100, closed_at=dt.datetime(2026, 1, 1))]

    metrics = compute_performance_metrics(trades, capital=100_000)

    assert metrics.sharpe_ratio is None


def test_sharpe_ratio_across_two_trading_days():
    day1 = dt.datetime(2026, 1, 1, 10, 0)
    day2 = dt.datetime(2026, 1, 2, 10, 0)
    trades = [
        make_trade(1000, closed_at=day1),
        make_trade(-500, closed_at=day2),
        make_trade(200, closed_at=day2 + dt.timedelta(hours=1)),
    ]

    metrics = compute_performance_metrics(trades, capital=100_000)

    assert metrics.sharpe_ratio == pytest.approx(6.0442, abs=0.001)


def test_sharpe_ratio_is_none_when_capital_is_zero():
    trades = [
        make_trade(100, closed_at=dt.datetime(2026, 1, 1)),
        make_trade(-50, closed_at=dt.datetime(2026, 1, 2)),
    ]

    metrics = compute_performance_metrics(trades, capital=0)

    assert metrics.sharpe_ratio is None
    assert metrics.max_drawdown_pct is None


def test_winning_losing_counts_and_avg_win_loss():
    trades = [make_trade(100), make_trade(-50), make_trade(80), make_trade(-120), make_trade(30)]

    metrics = compute_performance_metrics(trades, capital=100_000)

    assert metrics.winning_trades == 3
    assert metrics.losing_trades == 2
    assert metrics.avg_win == pytest.approx(210 / 3)
    assert metrics.avg_loss == pytest.approx(-170 / 2)


def test_avg_win_avg_loss_none_when_no_trades_yet():
    metrics = compute_performance_metrics([], capital=100_000)

    assert metrics.avg_win is None
    assert metrics.avg_loss is None


def test_equity_curve_daily_buckets_one_point_per_day():
    day1 = dt.datetime(2026, 1, 1, 10, 0)
    day2 = dt.datetime(2026, 1, 2, 10, 0)
    trades = [
        make_trade(100, closed_at=day1),
        make_trade(-30, closed_at=day1 + dt.timedelta(hours=1)),
        make_trade(50, closed_at=day2),
    ]

    points = equity_curve(trades, bucket="daily")

    assert [p.bucket for p in points] == [day1.date(), day2.date()]
    assert points[0].cumulative_pnl == pytest.approx(70)
    assert points[1].cumulative_pnl == pytest.approx(120)


def test_equity_curve_monthly_bucketing_collapses_same_month():
    trades = [
        make_trade(100, closed_at=dt.datetime(2026, 1, 5)),
        make_trade(50, closed_at=dt.datetime(2026, 1, 25)),
        make_trade(-20, closed_at=dt.datetime(2026, 2, 1)),
    ]

    points = equity_curve(trades, bucket="monthly")

    assert [p.bucket for p in points] == [dt.date(2026, 1, 1), dt.date(2026, 2, 1)]
    assert points[0].cumulative_pnl == pytest.approx(150)
    assert points[1].cumulative_pnl == pytest.approx(130)


def test_pnl_by_period_is_net_per_bucket_not_cumulative():
    trades = [
        make_trade(100, closed_at=dt.datetime(2026, 1, 5)),
        make_trade(-40, closed_at=dt.datetime(2026, 1, 25)),
        make_trade(70, closed_at=dt.datetime(2026, 2, 1)),
    ]

    periods = pnl_by_period(trades, bucket="monthly")

    assert len(periods) == 2
    assert periods[0].bucket == dt.date(2026, 1, 1)
    assert periods[0].pnl == pytest.approx(60)
    assert periods[1].bucket == dt.date(2026, 2, 1)
    assert periods[1].pnl == pytest.approx(70)


def test_drawdown_series_matches_max_drawdown():
    trades = [make_trade(100), make_trade(-50), make_trade(80), make_trade(-120), make_trade(30)]

    series = drawdown_series(trades, capital=100_000)
    metrics = compute_performance_metrics(trades, capital=100_000)

    assert [round(p.drawdown, 2) for p in series] == [0, 50, 0, 120, 90]
    assert max(p.drawdown for p in series) == metrics.max_drawdown
    assert series[3].drawdown_pct == pytest.approx(0.12)


def test_profit_distribution_buckets_all_trades():
    trades = [make_trade(pnl) for pnl in [10, 20, 30, 40, 50]]

    buckets = profit_distribution(trades, bucket_count=5)

    assert sum(b.count for b in buckets) == 5
    assert buckets[0].range_start == 10
    assert buckets[-1].range_end == 50


def test_profit_distribution_empty_when_no_trades():
    assert profit_distribution([]) == []


def test_profit_distribution_single_bucket_when_all_pnls_equal():
    trades = [make_trade(25), make_trade(25), make_trade(25)]

    buckets = profit_distribution(trades)

    assert len(buckets) == 1
    assert buckets[0].count == 3


def test_rolling_sharpe_empty_when_no_capital_or_trades():
    trades = [make_trade(100, closed_at=dt.datetime(2026, 1, 1))]

    assert rolling_sharpe([], capital=100_000) == []
    assert rolling_sharpe(trades, capital=0) == []


def test_rolling_sharpe_one_point_per_trading_day():
    day1 = dt.datetime(2026, 1, 1)
    day2 = dt.datetime(2026, 1, 2)
    day3 = dt.datetime(2026, 1, 3)
    trades = [
        make_trade(1000, closed_at=day1),
        make_trade(-500, closed_at=day2),
        make_trade(200, closed_at=day3),
    ]

    points = rolling_sharpe(trades, capital=100_000, window_days=2)

    assert [p.date for p in points] == [day1.date(), day2.date(), day3.date()]
    # First day alone: fewer than 2 return observations in its window -> None
    assert points[0].sharpe_ratio is None
    # Each later window has exactly 2 trading days of returns -> a value
    assert points[1].sharpe_ratio is not None
    assert points[2].sharpe_ratio is not None
