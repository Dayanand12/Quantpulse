"""Default IStrategyRegistry: scans a directory of *.py files, imports
each one, and registers any class defined there that implements
IStrategy.

Adding a new strategy is: drop a file in strategies/ with a class shaped
like strategies/orb_reversal.py::ORBReversalStrategy. Nothing else to
register or edit — this discovers it automatically at next startup
(restart-to-apply, same as watchlist/deployment changes).

Takes an explicit `directory` (defaulting to the real strategies/ package)
rather than always scanning the installed package, so tests can point it
at an isolated tmp directory instead of depending on whatever happens to
be in the real project's strategies/ folder.
"""

import importlib.util
import inspect
import logging
import sys
import uuid
from pathlib import Path
from typing import Dict, List, Optional

import strategies as strategies_package
from core.application.interfaces.strategy import IStrategy
from core.application.interfaces.strategy_registry import IStrategyRegistry
from core.exceptions import NotFoundError

logger = logging.getLogger(__name__)


class FileStrategyRegistry(IStrategyRegistry):
    def __init__(self, directory: Optional[Path] = None) -> None:
        self._directory = directory or Path(strategies_package.__path__[0])
        # Cached instances (list_strategies() only reads name/display_name/
        # side off these — never .screen()s them, so sharing is harmless)
        # and the classes behind them, kept separately so get_strategy()
        # can hand out a FRESH instance per call instead of these cached
        # ones — see get_strategy()'s docstring for why that distinction
        # matters.
        self._strategies: Dict[str, IStrategy] = {}
        self._strategy_classes: Dict[str, type] = {}
        self._discover()

    def _discover(self) -> None:
        for path in sorted(self._directory.glob("*.py")):
            if path.stem == "__init__":
                continue

            # A broken/WIP strategy file (bad syntax, an invalid
            # conditions.json — see core/domain/strategy_conditions.py)
            # must never take every OTHER strategy down with it, since
            # this registry backs live/paper trading (core/container.py):
            # one bad backtest-only experiment can't be allowed to crash
            # every already-deployed strategy's startup.
            try:
                self._load_one(path)
            except Exception as e:
                logger.warning("Skipping strategy file %s: %s", path.name, e)

    def _load_one(self, path: Path) -> None:
        # Unique synthetic module name per load — avoids clashing with
        # the real `strategies.*` package when scanning a different
        # (e.g. test) directory.
        module_name = f"_strategy_registry_{uuid.uuid4().hex}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj is IStrategy or not issubclass(obj, IStrategy):
                continue
            if obj.__module__ != module_name:
                continue  # only classes defined here, not ones merely imported into it

            instance = obj()
            self._strategies[instance.name] = instance
            self._strategy_classes[instance.name] = obj

    def list_strategies(self) -> List[IStrategy]:
        return list(self._strategies.values())

    def get_strategy(self, name: str) -> IStrategy:
        """A FRESH instance every call — never the cached one
        list_strategies() hands out.

        core/container.py::build_deployment_runtime calls this once per
        deployment, and a JsonConditionStrategy instance carries mutable
        per-symbol crossing-condition state (ConditionSet._previous, see
        core/domain/strategy_conditions.py) that must never be shared
        across deployments. Multiple deployments commonly reference the
        same strategy_name at different timeframes, all reading/writing
        the SAME symbols out of one shared watchlist (see Deployment's
        docstring) — sharing one instance's crossing-state between them
        would interleave two different timeframes' bars into what looks
        like one continuous price history, corrupting "did ltp cross
        above orb_high" for every deployment involved. Confirmed for
        real: 13 strategy variants deployed across 64 (mostly
        multi-timeframe) deployments over a shared 50-symbol watchlist
        produced ~1 live trade in a day and a half, while backtesting the
        exact same conditions against a 15-symbol sample over 2 months
        (which builds a fresh instance per single-symbol/single-timeframe
        run, so never hits this) produced 185 trades from a fifth of that
        combo/symbol space — a gap far too large to be "the market just
        didn't set up," and gone once this returns a fresh instance."""
        try:
            cls = self._strategy_classes[name]
        except KeyError:
            raise NotFoundError(f"Unknown strategy: {name}")
        return cls()
