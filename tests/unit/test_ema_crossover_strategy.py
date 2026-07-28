from strategies.ema_crossover import EmaCrossoverStrategy


def row(ema5, ema9):
    return {"ltp": 100.0, "ema5": ema5, "ema9": ema9}


def test_screen_returns_nothing_on_first_tick_even_if_already_crossed():
    strategy = EmaCrossoverStrategy()
    snapshot = {"RELIANCE": row(ema5=10.0, ema9=9.0)}

    assert strategy.screen(snapshot, ["RELIANCE"]) == []


def test_screen_fires_on_the_tick_ema5_crosses_above_ema9():
    strategy = EmaCrossoverStrategy()

    strategy.screen({"RELIANCE": row(ema5=9.0, ema9=10.0)}, ["RELIANCE"])
    result = strategy.screen({"RELIANCE": row(ema5=10.5, ema9=10.0)}, ["RELIANCE"])

    assert result == ["RELIANCE"]


def test_screen_does_not_refire_while_still_above():
    strategy = EmaCrossoverStrategy()

    strategy.screen({"RELIANCE": row(ema5=9.0, ema9=10.0)}, ["RELIANCE"])
    strategy.screen({"RELIANCE": row(ema5=10.5, ema9=10.0)}, ["RELIANCE"])
    result = strategy.screen({"RELIANCE": row(ema5=11.0, ema9=10.0)}, ["RELIANCE"])

    assert result == []


def test_screen_ignores_symbol_with_missing_ema_data():
    strategy = EmaCrossoverStrategy()
    snapshot = {"RELIANCE": {"ltp": 100.0, "ema5": None, "ema9": None}}

    assert strategy.screen(snapshot, ["RELIANCE"]) == []


def test_screen_tracks_multiple_symbols_independently():
    strategy = EmaCrossoverStrategy()

    strategy.screen(
        {
            "RELIANCE": row(ema5=9.0, ema9=10.0),
            "TCS": row(ema5=11.0, ema9=10.0),
        },
        ["RELIANCE", "TCS"],
    )
    result = strategy.screen(
        {
            "RELIANCE": row(ema5=10.5, ema9=10.0),  # crosses up now
            "TCS": row(ema5=10.5, ema9=10.0),  # was already above, no cross
        },
        ["RELIANCE", "TCS"],
    )

    assert result == ["RELIANCE"]
