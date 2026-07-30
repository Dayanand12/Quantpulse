from core.domain.models import Deployment, StrategyConfig
from infrastructure.persistence.database import Base, create_session_factory
from infrastructure.persistence.sql_deployment_repository import SqlDeploymentRepository


def make_repo(tmp_path):
    db_path = tmp_path / "test.db"
    session_factory = create_session_factory(f"sqlite:///{db_path}")
    Base.metadata.create_all(session_factory().get_bind())
    return SqlDeploymentRepository(session_factory)


def make_deployment(**overrides):
    defaults = dict(
        id="dep1",
        strategy_name="orb_reversal",
        symbols=("RELIANCE", "TCS"),
        capital=50_000.0,
        config=StrategyConfig(),
    )
    defaults.update(overrides)
    return Deployment(**defaults)


def test_list_is_empty_when_nothing_saved(tmp_path):
    repo = make_repo(tmp_path)

    assert repo.list_deployments() == []


def test_save_and_get_round_trip(tmp_path):
    repo = make_repo(tmp_path)
    deployment = make_deployment()

    repo.save_deployment(deployment)

    assert repo.get_deployment("dep1") == deployment
    assert repo.list_deployments() == [deployment]


def test_get_unknown_id_returns_none(tmp_path):
    repo = make_repo(tmp_path)

    assert repo.get_deployment("nope") is None


def test_save_upserts_by_id(tmp_path):
    repo = make_repo(tmp_path)
    repo.save_deployment(make_deployment(capital=50_000.0))

    repo.save_deployment(make_deployment(capital=75_000.0))

    assert len(repo.list_deployments()) == 1
    assert repo.get_deployment("dep1").capital == 75_000.0


def test_delete_removes_deployment(tmp_path):
    repo = make_repo(tmp_path)
    repo.save_deployment(make_deployment())

    repo.delete_deployment("dep1")

    assert repo.list_deployments() == []


def test_delete_unknown_id_is_a_noop(tmp_path):
    repo = make_repo(tmp_path)

    repo.delete_deployment("nope")  # must not raise

    assert repo.list_deployments() == []


def test_multiple_deployments_persist_independently(tmp_path):
    repo = make_repo(tmp_path)
    repo.save_deployment(make_deployment(id="dep1", symbols=("RELIANCE",)))
    repo.save_deployment(make_deployment(id="dep2", symbols=("INFY", "SBIN"), capital=20_000.0))

    ids = {d.id for d in repo.list_deployments()}

    assert ids == {"dep1", "dep2"}
    assert repo.get_deployment("dep2").symbols == ("INFY", "SBIN")


def test_start_end_time_round_trip(tmp_path):
    repo = make_repo(tmp_path)
    repo.save_deployment(
        make_deployment(config=StrategyConfig(start_time="09:15", end_time="10:45"))
    )

    saved = repo.get_deployment("dep1")

    assert saved.config.start_time == "09:15"
    assert saved.config.end_time == "10:45"


def test_start_end_time_default_when_not_specified(tmp_path):
    repo = make_repo(tmp_path)
    repo.save_deployment(make_deployment())

    saved = repo.get_deployment("dep1")

    assert saved.config.start_time == "09:20"
    assert saved.config.end_time == "11:30"


def test_timeframe_round_trip(tmp_path):
    repo = make_repo(tmp_path)
    repo.save_deployment(make_deployment(config=StrategyConfig(timeframe="15minute")))

    saved = repo.get_deployment("dep1")

    assert saved.config.timeframe == "15minute"


def test_timeframe_defaults_to_minute_when_not_specified(tmp_path):
    repo = make_repo(tmp_path)
    repo.save_deployment(make_deployment())

    saved = repo.get_deployment("dep1")

    assert saved.config.timeframe == "minute"
