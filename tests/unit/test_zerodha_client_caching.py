from unittest.mock import MagicMock

import Data_ingestion.client as client_module
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


def test_find_instrument_returns_token_and_exchange():
    client = make_client(instruments_by_exchange={
        "NSE": [{"tradingsymbol": "RELIANCE", "instrument_token": 738561, "exchange": "NSE"}],
    })

    assert client.find_instrument("RELIANCE", "NSE") == {
        "instrument_token": 738561,
        "exchange": "NSE",
    }


def test_find_instrument_falls_back_to_global_instruments():
    client = make_client(
        instruments_by_exchange={"NSE": []},
        global_instruments=[
            {"tradingsymbol": "NIFTY24AUG24000CE", "instrument_token": 12345, "exchange": "NFO"}
        ],
    )

    assert client.find_instrument("NIFTY24AUG24000CE", "NSE") == {
        "instrument_token": 12345,
        "exchange": "NFO",
    }


def test_find_instrument_returns_none_instead_of_raising():
    client = make_client(instruments_by_exchange={"NSE": []}, global_instruments=[])

    assert client.find_instrument("NOPE", "NSE") is None


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


def test_init_generates_token_only_after_kite_is_initialized(monkeypatch):
    events = []

    class FakeKiteConnect:
        def __init__(self, api_key):
            events.append(("kite_init", api_key))
            self.api_key = api_key

        def set_access_token(self, token):
            events.append(("set_token", token))

    class FakeKiteTicker:
        def __init__(self, api_key, access_token):
            events.append(("ticker_init", api_key, access_token))

    def fake_getenv(key, default=None):
        values = {
            "API_KEY": "demo-key",
            "API_SECRET": "demo-secret",
            "REDIRECT_URL": "http://127.0.0.1:5000/callback",
            "ACCESS_TOKEN": None,
        }
        return values.get(key, default)

    monkeypatch.setattr(client_module, "os", type("OsStub", (), {"getenv": staticmethod(fake_getenv)})())
    monkeypatch.setattr(client_module, "KiteConnect", FakeKiteConnect)
    monkeypatch.setattr(client_module, "KiteTicker", FakeKiteTicker)
    monkeypatch.setattr(ZerodhaClient, "_is_token_valid", lambda self, access_token: False)
    monkeypatch.setattr(ZerodhaClient, "_auto_generate_access_token", lambda self: "fresh-token")

    client = ZerodhaClient()

    assert client.access_token == "fresh-token"
    assert events[0] == ("kite_init", "demo-key")
    assert ("set_token", "fresh-token") in events
