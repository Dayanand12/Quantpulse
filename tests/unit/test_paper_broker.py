from runners.paper_trading.paper_broker import PaperBroker


def test_rejected_entries_is_empty_initially():
    broker = PaperBroker(initial_capital=50_000)

    assert broker.rejected_entries == {}


def test_entry_larger_than_capital_auto_downsizes_instead_of_rejecting():
    broker = PaperBroker(initial_capital=50_000)

    # 50 shares @ 2447 needs ~122,350 — more than the 50k budget.
    entered = broker.enter("TCS", "BUY", 2447.0, 50)

    assert entered is True
    assert broker.rejected_entries == {}
    assert broker.positions["TCS"]["qty"] == 20  # floor(50_000 / 2447)


def test_successful_entry_uses_requested_quantity_when_it_fits():
    broker = PaperBroker(initial_capital=50_000)

    entered = broker.enter("TCS", "BUY", 2447.0, 15)  # fits: ~36,705

    assert entered is True
    assert broker.positions["TCS"]["qty"] == 15
    assert broker.rejected_entries == {}


def test_each_symbol_sizes_against_its_own_full_capital_budget():
    # Regression: every symbol must get its own initial_capital-sized
    # allocation, independent of positions already opened this pass — the
    # shared available_capital pool must never starve later symbols.
    broker = PaperBroker(initial_capital=300_000)

    broker.enter("ADANIENT", "BUY", 2500.0, 500)  # downsizes to 120
    broker.enter("COALINDIA", "BUY", 400.0, 500)  # would starve if capital shared

    assert broker.positions["ADANIENT"]["qty"] == 120  # floor(300_000 / 2500)
    assert broker.positions["COALINDIA"]["qty"] == 500  # fits outright
    assert "COALINDIA" not in broker.rejected_entries


def test_market_snapshot_at_entry_carries_through_to_the_closed_trade():
    broker = PaperBroker(initial_capital=300_000)
    snapshot = {"ltp": 250.0, "rsi": 28.0, "adx": 31.0, "vwap": 248.0, "volume_ratio": 2.0}

    broker.enter("RELIANCE", "SELL", 250.0, 50, market_snapshot=snapshot)
    broker.exit("RELIANCE", 244.0)

    assert broker.trade_log[-1]["market_snapshot"] == snapshot


def test_market_snapshot_defaults_to_none_when_not_provided():
    broker = PaperBroker(initial_capital=300_000)

    broker.enter("RELIANCE", "SELL", 250.0, 50)
    broker.exit("RELIANCE", 244.0)

    assert broker.trade_log[-1]["market_snapshot"] is None


def test_entry_rejected_only_when_not_even_one_share_fits():
    broker = PaperBroker(initial_capital=50_000)

    entered = broker.enter("MRF", "BUY", 120_000.0, 1)  # single share > capital

    assert entered is False
    assert "MRF" in broker.rejected_entries
    rejection = broker.rejected_entries["MRF"]
    assert rejection["symbol"] == "MRF"
    assert rejection["side"] == "BUY"
    assert rejection["price"] == 120_000.0
    assert rejection["available_capital"] == 50_000
    assert rejection["reason"] == "insufficient_capital"
    assert rejection["at"] is not None


def test_rejection_clears_once_symbol_can_enter():
    broker = PaperBroker(initial_capital=50_000)

    assert broker.enter("MRF", "BUY", 120_000.0, 1) is False
    assert "MRF" in broker.rejected_entries

    # Capital budget increases (e.g. deployment edited + restarted).
    broker.initial_capital = 200_000
    assert broker.enter("MRF", "BUY", 120_000.0, 1) is True
    assert "MRF" not in broker.rejected_entries


def test_rejections_are_tracked_independently_per_symbol():
    broker = PaperBroker(initial_capital=50_000)

    broker.enter("MRF", "BUY", 120_000.0, 1)  # doesn't fit at all
    broker.enter("INFY", "BUY", 10.0, 10)  # fits fine

    assert set(broker.rejected_entries.keys()) == {"MRF"}


def test_status_includes_rejected_entries():
    broker = PaperBroker(initial_capital=50_000)
    broker.enter("MRF", "BUY", 120_000.0, 1)

    status = broker.status()

    assert "MRF" in status["rejected_entries"]
