# runners/backtesting/strategy_resolver.py
"""Resolves a strategy NAME (e.g. "orb_reversal") to its IStrategy class,
via a normal `import strategies.<name>` — not FileStrategyRegistry's
dynamic per-instance module trick (infrastructure/strategies/
file_strategy_registry.py), which creates a synthetic module name that
only exists in the importing process's sys.modules. That breaks two
things this package needs and the live app doesn't: multiprocessing
workers (runners/backtesting/parameter_sweep.py) can't re-import a
synthetic module when unpickling the class, and a second process (e.g.
the backtest API server, running independently of the live app) has no
way to resolve a class object handed to it by name only.

Shared by run_backtest.py (CLI) and backtest_server.py (API) so both
resolve strategies identically instead of drifting into two slightly
different discovery mechanisms.
"""

import importlib
import inspect
from pathlib import Path
from typing import List, Type

from core.application.interfaces.strategy import IStrategy

_STRATEGIES_DIR = Path(__file__).resolve().parent.parent.parent / "strategies"


class UnknownStrategyError(ValueError):
    pass


def list_strategy_names() -> List[str]:
    return sorted(p.stem for p in _STRATEGIES_DIR.glob("*.py") if p.stem != "__init__")


def resolve_strategy_class(name: str) -> Type[IStrategy]:
    try:
        module = importlib.import_module(f"strategies.{name}")
    except ModuleNotFoundError:
        raise UnknownStrategyError(
            f"Unknown strategy '{name}'. Available: {', '.join(list_strategy_names())}"
        ) from None

    for _, obj in inspect.getmembers(module, inspect.isclass):
        if obj is not IStrategy and issubclass(obj, IStrategy) and obj.__module__ == module.__name__:
            return obj

    raise UnknownStrategyError(f"No IStrategy subclass found in strategies/{name}.py")
