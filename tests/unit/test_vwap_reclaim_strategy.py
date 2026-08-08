from strategies.vwap_reclaim import VwapReclaimStrategy


def qualifying_row(ltp=105.0, adx=30):
    return {
        "ltp": ltp,
        "vwap": 100.0,
        "ema9": 106.0,
        "ema21": 104.0,
        "volume_ratio": 2.0,
        "adx": adx,
    }


def screen_after_reclaim(strategy, symbol="RELIANCE", row=None):
    """screen() only fires on the crossing tick itself — feed one
    below-VWAP tick first so the strategy has a `was_below` baseline,
    then the qualifying (now above-VWAP) tick."""
    row = row or qualifying_row()
    below = dict(row, ltp=95.0)  # below vwap=100.0
    strategy.screen({symbol: below}, [symbol])
    return strategy.screen({symbol: row}, [symbol])


def test_screen_returns_symbol_on_reclaim_with_all_conditions_met():
    strategy = VwapReclaimStrategy()
    assert screen_after_reclaim(strategy) == ["RELIANCE"]


def test_screen_excludes_symbol_failing_adx_filter():
    strategy = VwapReclaimStrategy()
    row = qualifying_row(adx=20)  # below ADX_THRESHOLD (25)

    assert screen_after_reclaim(strategy, row=row) == []


def test_screen_excludes_symbol_at_adx_threshold_boundary():
    strategy = VwapReclaimStrategy()
    exactly_at_threshold = qualifying_row(adx=25)
    just_below = qualifying_row(adx=24.99)

    assert screen_after_reclaim(strategy, "AT_THRESHOLD", exactly_at_threshold) == ["AT_THRESHOLD"]
    assert screen_after_reclaim(strategy, "JUST_BELOW", just_below) == []


def test_screen_excludes_symbol_missing_adx():
    strategy = VwapReclaimStrategy()
    row = qualifying_row()
    row["adx"] = None

    assert screen_after_reclaim(strategy, row=row) == []


def test_screen_excludes_symbol_failing_volume_filter():
    strategy = VwapReclaimStrategy()
    row = qualifying_row()
    row["volume_ratio"] = 1.0  # below VOLUME_RATIO_THRESHOLD (1.5)

    assert screen_after_reclaim(strategy, row=row) == []


def test_screen_excludes_symbol_not_trending_up():
    strategy = VwapReclaimStrategy()
    row = qualifying_row()
    row["ema9"] = 103.0  # below ema21 (104.0)

    assert screen_after_reclaim(strategy, row=row) == []


def test_screen_requires_an_actual_crossing_not_just_being_above_vwap():
    strategy = VwapReclaimStrategy()
    row = qualifying_row()

    # No prior tick fed first — no "was_below" baseline yet, so this must
    # not fire even though every other condition is met.
    assert strategy.screen({"RELIANCE": row}, ["RELIANCE"]) == []


def test_screen_does_not_refire_while_already_above_vwap():
    strategy = VwapReclaimStrategy()
    row = qualifying_row()

    assert screen_after_reclaim(strategy, row=row) == ["RELIANCE"]
    # Second consecutive above-VWAP tick — not a fresh crossing.
    assert strategy.screen({"RELIANCE": row}, ["RELIANCE"]) == []
