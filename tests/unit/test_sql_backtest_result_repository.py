import datetime as dt

from core.domain.backtest_result import BacktestRunParams
from infrastructure.persistence.database import Base, create_session_factory
from infrastructure.persistence.sql_backtest_result_repository import SqlBacktestResultRepository


def make_repo(tmp_path):
    db_path = tmp_path / "test.db"
    session_factory = create_session_factory(f"sqlite:///{db_path}")
    Base.metadata.create_all(session_factory().get_bind())
    return SqlBacktestResultRepository(session_factory)


def make_params(**overrides):
    defaults = dict(
        strategy_name="orb_reversal",
        symbols="WATCHLIST",
        timeframe="minute",
        date_from=dt.date(2024, 1, 1),
        date_to=dt.date(2024, 12, 31),
        quantity=50,
        stoploss_pct=0.8,
        target_pct=2.0,
        trailing_pct=0.1,
        max_cycles_per_day=10,
        start_time="09:20",
        end_time="11:30",
        charges_enabled=True,
        strategy_params_json="",
    )
    defaults.update(overrides)
    return BacktestRunParams(**defaults)


def test_save_then_get_round_trip(tmp_path):
    repo = make_repo(tmp_path)

    saved = repo.save_result(make_params(), {"total_trades": 5})

    fetched = repo.get_result(saved.id)
    assert fetched.result == {"total_trades": 5}
    assert fetched.params.strategy_name == "orb_reversal"


def test_save_identical_params_upserts_not_duplicates(tmp_path):
    repo = make_repo(tmp_path)
    first = repo.save_result(make_params(), {"total_trades": 5})

    second = repo.save_result(make_params(), {"total_trades": 7})

    assert second.id == first.id
    assert len(repo.list_results("orb_reversal")) == 1
    assert repo.get_result(first.id).result == {"total_trades": 7}


def test_save_different_params_creates_a_new_row(tmp_path):
    repo = make_repo(tmp_path)
    repo.save_result(make_params(stoploss_pct=0.8), {"total_trades": 5})

    repo.save_result(make_params(stoploss_pct=1.0), {"total_trades": 9})

    assert len(repo.list_results("orb_reversal")) == 2


def test_get_unknown_id_returns_none(tmp_path):
    repo = make_repo(tmp_path)

    assert repo.get_result(999) is None


def test_delete_result_removes_it(tmp_path):
    repo = make_repo(tmp_path)
    saved = repo.save_result(make_params(), {"total_trades": 5})

    repo.delete_result(saved.id)

    assert repo.get_result(saved.id) is None
    assert repo.list_results("orb_reversal") == []


def test_delete_unknown_id_is_a_noop(tmp_path):
    repo = make_repo(tmp_path)

    repo.delete_result(999)  # must not raise
