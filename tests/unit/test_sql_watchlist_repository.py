import pytest

from infrastructure.persistence.database import Base, create_session_factory
from infrastructure.persistence.sql_watchlist_repository import SqlWatchlistRepository


def make_repo(tmp_path):
    db_path = tmp_path / "test.db"
    session_factory = create_session_factory(f"sqlite:///{db_path}")
    Base.metadata.create_all(session_factory().get_bind())
    return SqlWatchlistRepository(session_factory)


def test_list_watchlists_returns_empty_when_none_created(tmp_path):
    repo = make_repo(tmp_path)

    assert repo.list_watchlists() == []


def test_create_and_save_round_trip(tmp_path):
    repo = make_repo(tmp_path)

    watchlist = repo.create_watchlist("Nifty50")
    repo.save_symbols(watchlist.id, ["reliance", "tcs", "infy"])

    assert repo.get_symbols(watchlist.id) == ["RELIANCE", "TCS", "INFY"]
    [listed] = repo.list_watchlists()
    assert listed.name == "Nifty50"
    assert listed.symbols == ("RELIANCE", "TCS", "INFY")


def test_save_cleans_blanks_duplicates_and_case(tmp_path):
    repo = make_repo(tmp_path)
    watchlist = repo.create_watchlist("Group")

    repo.save_symbols(watchlist.id, ["reliance", " RELIANCE ", "", "  ", "tcs"])

    assert repo.get_symbols(watchlist.id) == ["RELIANCE", "TCS"]


def test_save_replaces_previous_symbols(tmp_path):
    repo = make_repo(tmp_path)
    watchlist = repo.create_watchlist("Group")

    repo.save_symbols(watchlist.id, ["RELIANCE", "TCS"])
    repo.save_symbols(watchlist.id, ["INFY"])

    assert repo.get_symbols(watchlist.id) == ["INFY"]


def test_create_watchlist_rejects_duplicate_name(tmp_path):
    repo = make_repo(tmp_path)
    repo.create_watchlist("Group")

    with pytest.raises(ValueError):
        repo.create_watchlist("Group")


def test_rename_watchlist(tmp_path):
    repo = make_repo(tmp_path)
    watchlist = repo.create_watchlist("Old Name")

    renamed = repo.rename_watchlist(watchlist.id, "New Name")

    assert renamed.name == "New Name"
    assert repo.list_watchlists()[0].name == "New Name"


def test_rename_rejects_conflicting_name(tmp_path):
    repo = make_repo(tmp_path)
    repo.create_watchlist("A")
    b = repo.create_watchlist("B")

    with pytest.raises(ValueError):
        repo.rename_watchlist(b.id, "A")


def test_delete_watchlist_removes_it_and_its_symbols(tmp_path):
    repo = make_repo(tmp_path)
    a = repo.create_watchlist("A")
    repo.create_watchlist("B")
    repo.save_symbols(a.id, ["RELIANCE"])

    repo.delete_watchlist(a.id)

    assert [w.name for w in repo.list_watchlists()] == ["B"]


def test_delete_rejects_the_last_remaining_watchlist(tmp_path):
    repo = make_repo(tmp_path)
    only = repo.create_watchlist("Only")

    with pytest.raises(ValueError):
        repo.delete_watchlist(only.id)


def test_get_all_symbols_is_deduplicated_union_across_watchlists(tmp_path):
    repo = make_repo(tmp_path)
    a = repo.create_watchlist("A")
    b = repo.create_watchlist("B")
    repo.save_symbols(a.id, ["RELIANCE", "TCS"])
    repo.save_symbols(b.id, ["TCS", "INFY"])

    assert repo.get_all_symbols() == ["RELIANCE", "TCS", "INFY"]


def test_operations_on_unknown_watchlist_id_raise(tmp_path):
    repo = make_repo(tmp_path)

    with pytest.raises(ValueError):
        repo.save_symbols(999, ["RELIANCE"])
    with pytest.raises(ValueError):
        repo.rename_watchlist(999, "X")
    with pytest.raises(ValueError):
        repo.delete_watchlist(999)
