from pathlib import Path

import pytest

from core.exceptions import ValidationError
from infrastructure.strategies.filesystem_strategy_source_repository import (
    FilesystemStrategySourceRepository,
)
from runners.backtesting.strategy_cloner import clone_strategy
from runners.backtesting.strategy_resolver import resolve_strategy_class

# clone_strategy resolves the base strategy via a real `import
# strategies.<name>` (runners/backtesting/strategy_resolver.py) — unlike
# FilesystemStrategySourceRepository's own tests, this can't point at an
# isolated tmp_path; it has to use a real name already in strategies/ and
# clean up the file it creates there afterward.
STRATEGIES_DIR = Path(__file__).resolve().parent.parent.parent / "strategies"
BASE_STRATEGY = "test_always_short"


@pytest.fixture
def source_repo():
    return FilesystemStrategySourceRepository(STRATEGIES_DIR)


@pytest.fixture
def cleanup_clone():
    created = []
    yield created
    for name in created:
        path = STRATEGIES_DIR / f"{name}.py"
        if path.exists():
            path.unlink()


def test_clone_creates_a_new_file_with_updated_name(source_repo, cleanup_clone):
    cleanup_clone.append("test_always_short_clone_a")

    clone_strategy(source_repo, BASE_STRATEGY, "test_always_short_clone_a")

    cls = resolve_strategy_class("test_always_short_clone_a")
    instance = cls()
    assert instance.name == "test_always_short_clone_a"
    assert "[test_always_short_clone_a]" in instance.display_name
    # side/behavior carried over unchanged from the base strategy
    assert instance.side.value == "SELL"


def test_clone_does_not_modify_the_base_strategy(source_repo, cleanup_clone):
    cleanup_clone.append("test_always_short_clone_b")
    original_source = source_repo.get_source(BASE_STRATEGY)

    clone_strategy(source_repo, BASE_STRATEGY, "test_always_short_clone_b")

    assert source_repo.get_source(BASE_STRATEGY) == original_source


def test_clone_rejects_a_name_that_already_exists(source_repo, cleanup_clone):
    cleanup_clone.append("test_always_short_clone_c")
    clone_strategy(source_repo, BASE_STRATEGY, "test_always_short_clone_c")

    with pytest.raises(ValidationError):
        clone_strategy(source_repo, BASE_STRATEGY, "test_always_short_clone_c")


def test_clone_rejects_an_invalid_name(source_repo, cleanup_clone):
    with pytest.raises(ValidationError):
        clone_strategy(source_repo, BASE_STRATEGY, "Not-A-Valid-Name")
