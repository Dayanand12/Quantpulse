from strategies.orb_reversal import ORBReversalStrategy


def qualifying_row(volume_ratio=2.0):
    return {
        "ltp": 250.0,
        "vwap": 255.0,
        "ema9": 251.0,
        "ema21": 253.0,
        "rsi": 40,
        "volume_ratio": volume_ratio,
        "atr_pct": 1.0,
        "adx": 25,
        "distance_to_or_low": 0.1,
    }


def test_screen_returns_symbol_that_passes_all_three_stages():
    strategy = ORBReversalStrategy()
    snapshot = {"RELIANCE": qualifying_row()}

    assert strategy.screen(snapshot, ["RELIANCE"]) == ["RELIANCE"]


def test_screen_excludes_symbol_failing_stage1():
    strategy = ORBReversalStrategy()
    row = qualifying_row()
    row["rsi"] = 60  # fails stage1 (rsi < 48)
    snapshot = {"RELIANCE": row}

    assert strategy.screen(snapshot, ["RELIANCE"]) == []


def test_screen_excludes_symbol_failing_stage2():
    strategy = ORBReversalStrategy()
    row = qualifying_row()
    row["volume_ratio"] = 1.0  # fails stage2 (volume_ratio >= 1.7)
    snapshot = {"RELIANCE": row}

    assert strategy.screen(snapshot, ["RELIANCE"]) == []


def test_screen_excludes_symbol_failing_stage3():
    strategy = ORBReversalStrategy()
    row = qualifying_row()
    row["distance_to_or_low"] = 5.0  # fails stage3 (-2.0 <= distance <= 2.0)
    snapshot = {"RELIANCE": row}

    assert strategy.screen(snapshot, ["RELIANCE"]) == []


def test_screen_ignores_symbols_outside_the_given_list():
    strategy = ORBReversalStrategy()
    snapshot = {"RELIANCE": qualifying_row(), "TCS": qualifying_row()}

    assert strategy.screen(snapshot, ["RELIANCE"]) == ["RELIANCE"]


def test_screen_ranks_by_volume_ratio_descending_and_caps_at_five():
    strategy = ORBReversalStrategy()
    symbols = [f"SYM{i}" for i in range(7)]
    snapshot = {sym: qualifying_row(volume_ratio=float(i)) for i, sym in enumerate(symbols)}

    result = strategy.screen(snapshot, symbols)

    assert len(result) == 5
    assert result[0] == "SYM6"  # highest volume_ratio first
    assert result[-1] == "SYM2"


def test_screen_skips_symbols_missing_from_snapshot():
    strategy = ORBReversalStrategy()
    snapshot = {"RELIANCE": qualifying_row()}

    assert strategy.screen(snapshot, ["RELIANCE", "GHOST"]) == ["RELIANCE"]
