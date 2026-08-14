from core.application.interfaces.symbol_master_repository import SymbolSuggestion
from infrastructure.persistence.database import Base, create_session_factory
from infrastructure.persistence.sql_symbol_master_repository import SqlSymbolMasterRepository


def make_repo(tmp_path):
    db_path = tmp_path / "test.db"
    session_factory = create_session_factory(f"sqlite:///{db_path}")
    Base.metadata.create_all(session_factory().get_bind())
    return SqlSymbolMasterRepository(session_factory)


SAMPLE = [
    SymbolSuggestion("RELIANCE", "Reliance Industries Ltd"),
    SymbolSuggestion("RELCAPITAL", "Reliance Capital Ltd"),
    SymbolSuggestion("TCS", "Tata Consultancy Services Ltd"),
    SymbolSuggestion("INFY", "Infosys Ltd"),
]


def test_search_empty_query_returns_nothing(tmp_path):
    repo = make_repo(tmp_path)
    repo.replace_all(SAMPLE)

    assert repo.search("") == []


def test_search_matches_tradingsymbol_prefix_first(tmp_path):
    repo = make_repo(tmp_path)
    repo.replace_all(SAMPLE)

    results = repo.search("REL")

    assert [r.tradingsymbol for r in results] == ["RELCAPITAL", "RELIANCE"]


def test_search_matches_company_name(tmp_path):
    repo = make_repo(tmp_path)
    repo.replace_all(SAMPLE)

    results = repo.search("Infosys")

    assert [r.tradingsymbol for r in results] == ["INFY"]


def test_search_is_case_insensitive(tmp_path):
    repo = make_repo(tmp_path)
    repo.replace_all(SAMPLE)

    assert [r.tradingsymbol for r in repo.search("tcs")] == ["TCS"]


def test_search_respects_limit(tmp_path):
    repo = make_repo(tmp_path)
    repo.replace_all(SAMPLE)

    assert len(repo.search("R", limit=1)) == 1


def test_replace_all_clears_previous_rows(tmp_path):
    repo = make_repo(tmp_path)
    repo.replace_all(SAMPLE)
    assert repo.count() == 4

    repo.replace_all([SymbolSuggestion("TCS", "Tata Consultancy Services Ltd")])

    assert repo.count() == 1


def test_count_reflects_stored_rows(tmp_path):
    repo = make_repo(tmp_path)
    assert repo.count() == 0

    repo.replace_all(SAMPLE)

    assert repo.count() == 4
