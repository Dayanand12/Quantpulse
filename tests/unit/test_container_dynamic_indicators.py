from core.container import _required_dynamic_indicators_for_deployments
from core.domain.models import Deployment, StrategyConfig

DYNAMIC_JSON = '{"conditions": [{"left": {"indicator": "ema", "params": {"period": 20}}, "op": ">", "right": {"value": 0}}]}'
BARE_JSON = '{"conditions": [{"left": "adx", "op": ">=", "right": {"value": 25}}]}'


def make_deployment(strategy_name: str, enabled: bool = True) -> Deployment:
    return Deployment(
        id=f"dep_{strategy_name}",
        strategy_name=strategy_name,
        symbols=("RELIANCE",),
        capital=100_000,
        config=StrategyConfig(),
        enabled=enabled,
    )


def test_collects_dynamic_indicators_from_an_enabled_deployment(tmp_path):
    (tmp_path / "strat_a.json").write_text(DYNAMIC_JSON, encoding="utf-8")
    deployments = [make_deployment("strat_a")]

    specs = _required_dynamic_indicators_for_deployments(deployments, strategies_dir=tmp_path)

    assert [s.key for s in specs] == ["ema_20"]


def test_disabled_deployment_contributes_nothing(tmp_path):
    (tmp_path / "strat_a.json").write_text(DYNAMIC_JSON, encoding="utf-8")
    deployments = [make_deployment("strat_a", enabled=False)]

    specs = _required_dynamic_indicators_for_deployments(deployments, strategies_dir=tmp_path)

    assert specs == []


def test_deduplicates_across_multiple_deployments(tmp_path):
    (tmp_path / "strat_a.json").write_text(DYNAMIC_JSON, encoding="utf-8")
    (tmp_path / "strat_b.json").write_text(DYNAMIC_JSON, encoding="utf-8")
    deployments = [make_deployment("strat_a"), make_deployment("strat_b")]

    specs = _required_dynamic_indicators_for_deployments(deployments, strategies_dir=tmp_path)

    assert [s.key for s in specs] == ["ema_20"]


def test_strategy_with_only_bare_fields_contributes_nothing(tmp_path):
    (tmp_path / "strat_a.json").write_text(BARE_JSON, encoding="utf-8")
    deployments = [make_deployment("strat_a")]

    specs = _required_dynamic_indicators_for_deployments(deployments, strategies_dir=tmp_path)

    assert specs == []


def test_strategy_with_no_conditions_json_contributes_nothing(tmp_path):
    deployments = [make_deployment("no_json_here")]

    specs = _required_dynamic_indicators_for_deployments(deployments, strategies_dir=tmp_path)

    assert specs == []
