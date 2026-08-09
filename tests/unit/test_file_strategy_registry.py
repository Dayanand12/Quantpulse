import pytest

from core.domain.enums import OrderSide
from core.exceptions import NotFoundError
from infrastructure.strategies.file_strategy_registry import FileStrategyRegistry

SAMPLE_STRATEGY_SOURCE = """
from typing import Dict, List

from core.application.interfaces.strategy import IStrategy
from core.domain.enums import OrderSide


class SampleStrategy(IStrategy):
    name = "sample_strategy"
    display_name = "Sample Strategy"
    side = OrderSide.BUY

    def screen(self, snapshot: Dict[str, dict], symbols: List[str]) -> List[str]:
        return []
"""


def make_registry(tmp_path, extra_files=()):
    (tmp_path / "sample_strategy.py").write_text(SAMPLE_STRATEGY_SOURCE, encoding="utf-8")
    for name, source in extra_files:
        (tmp_path / f"{name}.py").write_text(source, encoding="utf-8")
    return FileStrategyRegistry(tmp_path)


def test_discovers_strategy_from_directory(tmp_path):
    registry = make_registry(tmp_path)

    names = [s.name for s in registry.list_strategies()]

    assert names == ["sample_strategy"]


def test_get_strategy_returns_matching_instance(tmp_path):
    registry = make_registry(tmp_path)

    strategy = registry.get_strategy("sample_strategy")

    assert strategy.name == "sample_strategy"
    assert strategy.side == OrderSide.BUY


def test_get_strategy_raises_not_found_for_unknown_name(tmp_path):
    registry = make_registry(tmp_path)

    with pytest.raises(NotFoundError):
        registry.get_strategy("does_not_exist")


def test_ignores_init_file(tmp_path):
    (tmp_path / "__init__.py").write_text("", encoding="utf-8")

    registry = make_registry(tmp_path)

    assert [s.name for s in registry.list_strategies()] == ["sample_strategy"]


BROKEN_STRATEGY_SOURCE = """
from typing import Dict, List

from core.application.interfaces.strategy import IStrategy
from core.domain.enums import OrderSide


class BrokenStrategy(IStrategy):
    name = "broken_strategy"
    display_name = "Broken Strategy"
    side = OrderSide.BUY

    def __init__(self):
        raise RuntimeError("simulated construction failure")

    def screen(self, snapshot: Dict[str, dict], symbols: List[str]) -> List[str]:
        return []
"""


def test_a_broken_strategy_file_is_skipped_not_fatal(tmp_path):
    # This backs live/paper trading (core/container.py) — one malformed
    # strategy file (bad syntax, a construction error, an invalid
    # conditions.json) must never take every OTHER already-deployed
    # strategy down with it.
    registry = make_registry(tmp_path, extra_files=[("broken_strategy", BROKEN_STRATEGY_SOURCE)])

    names = [s.name for s in registry.list_strategies()]

    assert names == ["sample_strategy"]
    assert "broken_strategy" not in names


def test_real_strategies_directory_still_discovers_orb_reversal():
    """Sanity check the default (no directory override) still finds the
    real orb_reversal.py — proves the production wiring path works, while
    every other test above is isolated from it."""
    registry = FileStrategyRegistry()

    names = [s.name for s in registry.list_strategies()]

    assert "orb_reversal" in names
