from infrastructure.persistence.database import Base, create_session_factory
from infrastructure.persistence.sql_watchlist_repository import SqlWatchlistRepository


def make_repo(tmp_path):
    db_path = tmp_path / "test.db"
    session_factory = create_session_factory(f"sqlite:///{db_path}")
    Base.metadata.create_all(session_factory().get_bind())
    return SqlWatchlistRepository(session_factory)


def test_get_symbols_returns_empty_when_never_saved(tmp_path):
    repo = make_repo(tmp_path)

    assert repo.get_symbols() == []


def test_save_and_get_round_trip(tmp_path):
    repo = make_repo(tmp_path)

    repo.save_symbols(["reliance", "tcs", "infy"])

    assert repo.get_symbols() == ["RELIANCE", "TCS", "INFY"]


def test_save_cleans_blanks_duplicates_and_case(tmp_path):
    repo = make_repo(tmp_path)

    repo.save_symbols(["reliance", " RELIANCE ", "", "  ", "tcs"])

    assert repo.get_symbols() == ["RELIANCE", "TCS"]


def test_save_replaces_previous_watchlist(tmp_path):
    repo = make_repo(tmp_path)

    repo.save_symbols(["RELIANCE", "TCS"])
    repo.save_symbols(["INFY"])

    assert repo.get_symbols() == ["INFY"]
