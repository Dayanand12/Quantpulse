# backfill_per_symbol_results.py
"""One-time maintenance script: materializes a per-symbol backtest_results
row for every symbol already present in an existing stored result's
`by_symbol` breakdown.

Backtests now save one row PER SYMBOL going forward (see
runners/backtesting/result_persistence.py::save_per_symbol_results) instead
of one combined row for the whole symbol set — this lets the Analysis tab
filter/sort by individual symbol and makes dedup correctly per-symbol. That
change only applies to NEW runs; this script backfills the history that
already existed when it shipped, without re-running anything: every
already-stored result's `by_symbol` breakdown (computed at save time, from
the real trades) already holds each symbol's own aggregate metrics, so
splitting it out is just reading data that's already there.

The original combined rows are left in place, untouched — this is purely
additive. A combined row's own equity_curve/by_market_condition/by_side
were computed over ALL its symbols together, so there's no way to recover
a per-symbol equity curve or market-condition/side breakdown from it after
the fact (that needs the raw per-trade data, which was never persisted —
see core/domain/backtest_result.py's docstring). Backfilled per-symbol rows
therefore have an empty equity_curve/by_market_condition/by_side — same
"cheap to regenerate by re-running these exact params" tradeoff the rest
of this storage layer already makes, not a bug. Any NEW backtest saved
after this script runs gets a real per-symbol equity curve, same as
everything save_per_symbol_results produces going forward.

Usage:
    python backfill_per_symbol_results.py                  # every strategy
    python backfill_per_symbol_results.py --strategy vwap_reclaim
    python backfill_per_symbol_results.py --dry-run         # report only, no writes
"""

import argparse

from sqlalchemy import select

from core.domain.backtest_result import BacktestRunParams
from infrastructure.config.settings import get_settings
from infrastructure.persistence.database import create_session_factory, unit_of_work
from infrastructure.persistence.models import BacktestResultRecord
from infrastructure.persistence.sql_backtest_result_repository import SqlBacktestResultRepository


def _all_strategy_names(session_factory) -> list:
    with unit_of_work(session_factory) as session:
        rows = session.scalars(select(BacktestResultRecord.strategy_name).distinct())
        return sorted(set(rows))


def backfill(strategy_name: str = None, dry_run: bool = False) -> None:
    settings = get_settings()
    session_factory = create_session_factory(settings.database_url)
    result_repo = SqlBacktestResultRepository(session_factory)

    strategy_names = [strategy_name] if strategy_name else _all_strategy_names(session_factory)

    total_source_rows = 0
    total_per_symbol_rows = 0

    for name in strategy_names:
        existing = result_repo.list_results(name)
        # Skip rows that are already single-symbol (symbols_id already
        # matches what a per-symbol row would use) or have nothing to
        # split — only a genuine multi-symbol/"WATCHLIST" combined row
        # with more than one by_symbol entry (or a differently-keyed
        # single entry, e.g. a "WATCHLIST" run over just one symbol)
        # needs backfilling.
        for source in existing:
            by_symbol = source.result.get("by_symbol") or []
            if not by_symbol:
                continue
            if len(by_symbol) == 1 and source.params.symbols == by_symbol[0]["strategy_name"]:
                continue  # already exactly a per-symbol row

            total_source_rows += 1
            print(f"[{name}] result #{source.id} (symbols={source.params.symbols!r}) -> {len(by_symbol)} symbol(s)")

            if dry_run:
                total_per_symbol_rows += len(by_symbol)
                continue

            for entry in by_symbol:
                symbol = entry["strategy_name"]  # breakdown_rows reuses this field as the group key
                metrics = entry["metrics"]
                params = BacktestRunParams(
                    strategy_name=source.params.strategy_name,
                    symbols=symbol,
                    timeframe=source.params.timeframe,
                    date_from=source.params.date_from,
                    date_to=source.params.date_to,
                    quantity=source.params.quantity,
                    stoploss_pct=source.params.stoploss_pct,
                    target_pct=source.params.target_pct,
                    trailing_pct=source.params.trailing_pct,
                    max_cycles_per_day=source.params.max_cycles_per_day,
                    start_time=source.params.start_time,
                    end_time=source.params.end_time,
                    charges_enabled=source.params.charges_enabled,
                    strategy_params_json=source.params.strategy_params_json,
                )
                result_repo.save_result(params, {
                    "symbols_used": [symbol],
                    "symbols_missing_data": [],
                    "total_trades": metrics["total_trades"],
                    "metrics": metrics,
                    "equity_curve": [],
                    "by_symbol": [],
                    "by_market_condition": [],
                    "by_side": [],
                    "capital": source.result.get("capital", 0),
                })
                total_per_symbol_rows += 1

    verb = "Would create/update" if dry_run else "Created/updated"
    print(f"\n{verb} {total_per_symbol_rows} per-symbol result(s) from {total_source_rows} combined row(s).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", help="Only backfill this one strategy (default: every strategy).")
    parser.add_argument("--dry-run", action="store_true", help="Report what would happen without writing anything.")
    args = parser.parse_args()
    backfill(strategy_name=args.strategy, dry_run=args.dry_run)
