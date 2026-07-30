from live.paper_broker import PaperBroker


def test_rejected_entries_is_empty_initially():
    broker = PaperBroker(initial_capital=50_000)

    assert broker.rejected_entries == {}


def test_failed_entry_records_rejection():
    broker = PaperBroker(initial_capital=50_000)

    entered = broker.enter("TCS", "BUY", 2447.0, 50)  # needs ~122,350

    assert entered is False
    assert "TCS" in broker.rejected_entries
    rejection = broker.rejected_entries["TCS"]
    assert rejection["symbol"] == "TCS"
    assert rejection["side"] == "BUY"
    assert rejection["quantity"] == 50
    assert rejection["price"] == 2447.0
    assert rejection["required_capital"] == 2447.0 * 50
    assert rejection["available_capital"] == 50_000
    assert rejection["reason"] == "insufficient_capital"
    assert rejection["at"] is not None


def test_successful_entry_does_not_record_rejection():
    broker = PaperBroker(initial_capital=50_000)

    entered = broker.enter("TCS", "BUY", 2447.0, 15)  # fits: ~36,705

    assert entered is True
    assert broker.rejected_entries == {}


def test_rejection_clears_once_symbol_can_enter():
    broker = PaperBroker(initial_capital=50_000)

    assert broker.enter("TCS", "BUY", 2447.0, 50) is False
    assert "TCS" in broker.rejected_entries

    # Same symbol, now at a size that fits (e.g. after an edit+restart).
    assert broker.enter("TCS", "BUY", 2447.0, 15) is True
    assert "TCS" not in broker.rejected_entries


def test_rejections_are_tracked_independently_per_symbol():
    broker = PaperBroker(initial_capital=50_000)

    broker.enter("TCS", "BUY", 2447.0, 50)
    broker.enter("INFY", "BUY", 10.0, 10)  # fits fine

    assert set(broker.rejected_entries.keys()) == {"TCS"}


def test_status_includes_rejected_entries():
    broker = PaperBroker(initial_capital=50_000)
    broker.enter("TCS", "BUY", 2447.0, 50)

    status = broker.status()

    assert "TCS" in status["rejected_entries"]
