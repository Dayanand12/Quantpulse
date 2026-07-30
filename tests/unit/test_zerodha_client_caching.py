from unittest.mock import MagicMock

from Data_ingestion.client import ZerodhaClient


def make_client(instruments_by_exchange=None, global_instruments=None):
    """Bypasses __init__ (real construction needs API credentials / a
    browser login flow) — only wires up what get_instrument_token touches."""
    client = object.__new__(ZerodhaClient)
    client._instruments_cache = {}
    client.kite = MagicMock()
    client.kite.instruments.side_effect = (
        lambda exchange=None: (global_instruments or []) if exchange is None
        else (instruments_by_exchange or {}).get(exchange, [])
    )
    return client


def test_finds_token_on_exchange():
    client = make_client(instruments_by_exchange={
        "NSE": [{"tradingsymbol": "RELIANCE", "instrument_token": 123}],
    })

    assert client.get_instrument_token("RELIANCE", "NSE") == 123


def test_falls_back_to_global_instruments_for_indices():
    client = make_client(
        instruments_by_exchange={"NSE": []},
        global_instruments=[{"tradingsymbol": "NIFTY 50", "instrument_token": 256265}],
    )

    assert client.get_instrument_token("NIFTY 50", "NSE") == 256265


def test_raises_when_symbol_not_found_anywhere():
    client = make_client(instruments_by_exchange={"NSE": []}, global_instruments=[])

    try:
        client.get_instrument_token("NOPE", "NSE")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_instruments_are_only_fetched_once_per_exchange():
    client = make_client(instruments_by_exchange={
        "NSE": [{"tradingsymbol": "RELIANCE", "instrument_token": 123}],
    })

    client.get_instrument_token("RELIANCE", "NSE")
    client.get_instrument_token("RELIANCE", "NSE")
    client.get_instrument_token("RELIANCE", "NSE")

    # 1 call for "NSE" — the repeated lookups should hit the cache instead
    # of re-fetching Kite's full instrument dump every time.
    exchange_calls = [c for c in client.kite.instruments.call_args_list if c.args == ("NSE",)]
    assert len(exchange_calls) == 1
