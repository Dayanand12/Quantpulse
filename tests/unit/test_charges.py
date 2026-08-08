import dataclasses

from core.domain.charges import ChargeConfig, compute_charges
from core.domain.enums import OrderSide

DEFAULT = ChargeConfig()


def test_buy_trade_charges_brokerage_on_both_legs():
    breakdown = compute_charges(
        entry_price=100.0, exit_price=110.0, quantity=100, side=OrderSide.BUY, config=DEFAULT
    )
    entry_turnover = 100.0 * 100
    exit_turnover = 110.0 * 100
    expected_brokerage = min(entry_turnover * DEFAULT.brokerage_pct, DEFAULT.brokerage_max_per_order) + min(
        exit_turnover * DEFAULT.brokerage_pct, DEFAULT.brokerage_max_per_order
    )
    assert breakdown.brokerage == expected_brokerage


def test_brokerage_is_capped_per_order_on_large_trades():
    # Turnover large enough that 0.03% would exceed the ₹20 cap on each leg.
    breakdown = compute_charges(
        entry_price=1000.0, exit_price=1010.0, quantity=1000, side=OrderSide.BUY, config=DEFAULT
    )
    assert breakdown.brokerage == DEFAULT.brokerage_max_per_order * 2


def test_stt_applies_to_sell_leg_only_buy_trade():
    # BUY trade: entry is the buy leg, exit is the sell leg.
    breakdown = compute_charges(
        entry_price=100.0, exit_price=110.0, quantity=50, side=OrderSide.BUY, config=DEFAULT
    )
    exit_turnover = 110.0 * 50
    assert breakdown.stt == exit_turnover * DEFAULT.stt_pct


def test_stt_applies_to_sell_leg_only_sell_trade():
    # SELL (short) trade: entry is the sell leg, exit is the buy-to-cover leg.
    breakdown = compute_charges(
        entry_price=100.0, exit_price=90.0, quantity=50, side=OrderSide.SELL, config=DEFAULT
    )
    entry_turnover = 100.0 * 50
    assert breakdown.stt == entry_turnover * DEFAULT.stt_pct


def test_stamp_duty_applies_to_buy_leg_only():
    buy_trade = compute_charges(100.0, 110.0, 50, OrderSide.BUY, DEFAULT)
    sell_trade = compute_charges(100.0, 90.0, 50, OrderSide.SELL, DEFAULT)

    assert buy_trade.stamp_duty == 100.0 * 50 * DEFAULT.stamp_duty_pct  # entry (buy) leg
    assert sell_trade.stamp_duty == 90.0 * 50 * DEFAULT.stamp_duty_pct  # exit (buy) leg


def test_gst_is_percentage_of_brokerage_plus_exchange_charges():
    breakdown = compute_charges(100.0, 105.0, 50, OrderSide.BUY, DEFAULT)
    assert breakdown.gst == (breakdown.brokerage + breakdown.exchange_txn) * DEFAULT.gst_pct


def test_total_sums_every_component():
    breakdown = compute_charges(100.0, 105.0, 50, OrderSide.BUY, DEFAULT)
    assert breakdown.total == (
        breakdown.brokerage
        + breakdown.stt
        + breakdown.exchange_txn
        + breakdown.sebi
        + breakdown.stamp_duty
        + breakdown.gst
    )


def test_zero_rate_config_produces_zero_charges():
    zero_config = dataclasses.replace(
        DEFAULT,
        brokerage_pct=0,
        brokerage_max_per_order=0,
        stt_pct=0,
        exchange_txn_pct=0,
        sebi_pct=0,
        stamp_duty_pct=0,
        gst_pct=0,
    )
    breakdown = compute_charges(100.0, 105.0, 50, OrderSide.BUY, zero_config)
    assert breakdown.total == 0
