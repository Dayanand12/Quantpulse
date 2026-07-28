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
import sys
import uuid
from pathlib import Path
from typing import Dict, List, Optional

import strategies as strategies_package
from core.application.interfaces.strategy import IStrategy
from core.application.interfaces.strategy_registry import IStrategyRegistry
from core.exceptions import NotFoundError


class FileStrategyRegistry(IStrategyRegistry):
    def __init__(self, directory: Optional[Path] = None) -> None:
        self._directory = directory or Path(strategies_package.__path__[0])
        self._strategies: Dict[str, IStrategy] = {}
        self._discover()

    def _discover(self) -> None:
        for path in sorted(self._directory.glob("*.py")):
            if path.stem == "__init__":
                continue

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

    def list_strategies(self) -> List[IStrategy]:
        return list(self._strategies.values())

    def get_strategy(self, name: str) -> IStrategy:
        try:
            return self._strategies[name]
        except KeyError:
            raise NotFoundError(f"Unknown strategy: {name}")
