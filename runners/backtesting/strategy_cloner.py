# runners/backtesting/strategy_cloner.py
"""Clones an existing strategy file under a new name — the "tune a copy,
backtest it, promote to paper trading if it works" workflow, without
touching the original. Reuses FilesystemStrategySourceRepository (the
same read/write/validate path the Strategy Builder page already uses),
so a clone gets identical safety guarantees: path-traversal-safe names,
syntax checked before it ever hits disk, "already exists" caught cleanly.
"""

import re
from typing import Optional

from core.application.interfaces.strategy_params_repository import IStrategyParamsRepository
from core.application.interfaces.strategy_source_repository import IStrategySourceRepository
from runners.backtesting.strategy_resolver import resolve_strategy_class


def clone_strategy(
    source_repo: IStrategySourceRepository,
    base_name: str,
    new_name: str,
    params_repo: Optional[IStrategyParamsRepository] = None,
) -> str:
    """Copies base_name's source to a new file named new_name, with the
    `name`/`display_name` class attributes updated so the clone is a
    distinct, independently-selectable strategy in both the Backtest
    dropdown and the live app's Strategies page — not a second file that
    silently collides with the original's identity (see
    infrastructure/strategies/file_strategy_registry.py — it keys
    strategies by `name`, and a duplicate would let one overwrite the
    other with no error).

    If base_name has a conditions.json (core/domain/strategy_conditions.py)
    and params_repo is given, that gets copied to the clone too — so
    "clone, then tune the copy's indicator thresholds" works without
    silently falling back to the original's file."""
    base_cls = resolve_strategy_class(base_name)
    base_instance = base_cls()

    source = source_repo.get_source(base_name)

    new_source = re.sub(
        rf'(\bname\s*=\s*)"{re.escape(base_instance.name)}"',
        rf'\1"{new_name}"',
        source,
        count=1,
    )
    # Tag display_name too, so the clone reads as clearly distinct from
    # the original in every dropdown, not just distinguishable by the
    # internal name.
    new_source = re.sub(
        r'(\bdisplay_name\s*=\s*)"([^"]*)"',
        rf'\1"\2 [{new_name}]"',
        new_source,
        count=1,
    )

    source_repo.create_source(new_name, new_source)

    if params_repo is not None:
        base_params = params_repo.get_params(base_name)
        if base_params is not None:
            params_repo.create_params(new_name, base_params)

    return new_source
