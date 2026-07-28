import datetime as dt

import pytest

from core.domain.enums import OrderSide
from core.domain.metrics import compute_performance_metrics
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
