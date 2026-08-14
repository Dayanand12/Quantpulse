import pytest
from fastapi.testclient import TestClient

from infrastructure.config.settings import get_settings
from infrastructure.persistence.database import Base, create_session_factory
from infrastructure.persistence.sql_watchlist_repository import SqlWatchlistRepository


@pytest.fixture
def app_and_session_factory(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    get_settings.cache_clear()

    import backtest_server  # imports the ORM models onto Base before create_all

    session_factory = create_session_factory(f"sqlite:///{db_path}")
    Base.metadata.create_all(session_factory().get_bind())

    app = backtest_server.create_app()
    yield app, session_factory

    get_settings.cache_clear()


def test_watchlists_endpoint_lists_every_named_watchlist_separately(app_and_session_factory):
    app, session_factory = app_and_session_factory
    repo = SqlWatchlistRepository(session_factory)
    a = repo.create_watchlist("Nifty50")
    repo.save_symbols(a.id, ["RELIANCE", "TCS", "NIFTY 50"])
    b = repo.create_watchlist("Bank Stocks")
    repo.save_symbols(b.id, ["HDFCBANK", "ICICIBANK"])

    with TestClient(app) as client:
        res = client.get("/api/backtest/watchlists")

    assert res.status_code == 200
    by_name = {w["name"]: w for w in res.json()}
    # NIFTY 50 (the index) is filtered out — not tradeable, same rule
    # get_tradeable_watchlist_symbols() already applies to the union.
    assert by_name["Nifty50"]["symbols"] == ["RELIANCE", "TCS"]
    assert by_name["Bank Stocks"]["symbols"] == ["HDFCBANK", "ICICIBANK"]


def test_watchlist_union_endpoint_still_returns_everything_combined(app_and_session_factory):
    app, session_factory = app_and_session_factory
    repo = SqlWatchlistRepository(session_factory)
    a = repo.create_watchlist("A")
    repo.save_symbols(a.id, ["RELIANCE"])
    b = repo.create_watchlist("B")
    repo.save_symbols(b.id, ["TCS"])

    with TestClient(app) as client:
        res = client.get("/api/backtest/watchlist")

    assert res.status_code == 200
    assert set(res.json()["symbols"]) == {"RELIANCE", "TCS"}
