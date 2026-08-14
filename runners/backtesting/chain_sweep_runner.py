# runners/backtesting/chain_sweep_runner.py
"""Processes one ChainSweep's pending contracts to completion — meant to
run in a background thread (see backtest_server.py's chain-sweep create
endpoint), detached from whichever HTTP request started it, same
reasoning as runners/backtesting/batch_job_runner.py.

One risk/sizing config (sweep.shared_config) applies to EVERY contract —
unlike batch_job_runner.py, there's no per-item override to resolve, so
this doesn't need that module's group-by-settings-then-chunk machinery.
What IS reused: the pre-run dedup check against backtest_results (a
contract whose exact identity already has a stored row is marked
"skipped," not re-run) and saving progress after every chunk rather than
only at the end, so a browser close or a page reload never loses more
than one chunk's worth of work.

The actual backtest computation runs in a ProcessPoolExecutor, same
pattern as parameter_sweep.py/batch_runner.py already use for equity
sweeps -- a full option chain can be hundreds to low thousands of
contracts, and each one's run_backtest() is independent CPU-bound work
(fresh strategy instance, its own data), so this was previously leaving
every core but one idle. Workers only compute trades -- no DB access
inside a worker (SQLAlchemy sessions/connections aren't safe to share
across a process boundary), same reasoning as parameter_sweep.py's
_run_one; the main thread does every save (dedup check, save_per_symbol_
results, sweep_repo.save) as results complete via as_completed(), which
also gets incremental progress instead of pool.map()'s all-at-once return.
"""

import datetime as dt
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple, Type

from core.application.interfaces.backtest_result_repository import IBacktestResultRepository
from core.application.interfaces.chain_sweep_repository import IChainSweepRepository
from core.application.interfaces.strategy import IStrategy
from core.domain.backtest_result import BacktestRunParams
from core.domain.chain_sweep import ChainSweep, ChainSweepContract
from core.domain.charges import ChargeConfig, options_charge_config
from core.domain.indicator_registry import IndicatorSpec
from core.domain.models import OptionContract, StrategyConfig, Trade
from runners.backtesting.engine import run_backtest
from runners.backtesting.historical_loader import load_backtest_csv
from runners.backtesting.result_persistence import (
    read_strategy_params_json,
    required_dynamic_indicators,
    save_per_symbol_results,
)

SAVE_EVERY = 10
# See the PARALLEL_THRESHOLD usage below for the measurement behind this.
PARALLEL_THRESHOLD = 150


def _parse_date(value):
    return dt.date.fromisoformat(value) if value else None


def _config_from_settings(settings: Dict[str, Any]) -> StrategyConfig:
    return StrategyConfig(
        quantity=settings.get("quantity", 50),
        stoploss_pct=settings.get("stoploss_pct", 0.8),
        target_pct=settings.get("target_pct", 2.0),
        trailing_pct=settings.get("trailing_pct", 0.1),
        max_cycles_per_day=settings.get("max_cycles_per_day", 10),
        start_time=settings.get("start_time", "09:15"),
        end_time=settings.get("end_time", "15:30"),
        timeframe=settings.get("timeframe", "minute"),
    )


def _run_one_contract(args: tuple) -> Tuple[str, List[Trade]]:
    """Runs in a worker process. Pure computation only -- see module
    docstring for why DB access has to stay in the main thread."""
    (
        strategy_cls, symbol, csv_path, config, charge_config,
        date_from, date_to, extra_indicators,
    ) = args
    df = load_backtest_csv(csv_path)
    strategy = strategy_cls()
    trades = run_backtest(
        strategy, symbol, df, config, charge_config=charge_config,
        date_from=date_from, date_to=date_to, extra_indicators=extra_indicators,
    )
    return symbol, trades


def run_chain_sweep(
    sweep: ChainSweep,
    strategy_cls: Type[IStrategy],
    contract_csv_pairs: List[Tuple[OptionContract, str]],
    sweep_repo: IChainSweepRepository,
    result_repo: IBacktestResultRepository,
    max_workers: Optional[int] = None,
) -> None:
    try:
        sweep.status = "running"
        sweep_repo.save(sweep)

        settings = sweep.shared_config
        config = _config_from_settings(settings)
        charges_enabled = bool(settings.get("charges", True))
        charge_config: Optional[ChargeConfig] = options_charge_config() if charges_enabled else None
        requested_date_from = _parse_date(settings.get("date_from"))
        requested_date_to = _parse_date(settings.get("date_to"))
        extra_indicators: List[IndicatorSpec] = required_dynamic_indicators(sweep.strategy_name)
        strategy_params_json = read_strategy_params_json(sweep.strategy_name)
        capital = settings.get("capital", 100_000)

        # One list_results() call up front (this strategy's whole tuning
        # history) rather than a query per contract — same reasoning as
        # batch_job_runner.py::_find_already_tested.
        existing_by_identity: Dict[BacktestRunParams, Any] = {
            r.params: r for r in result_repo.list_results(sweep.strategy_name)
        }
        by_symbol = {c.symbol: (c, p) for c, p in contract_csv_pairs}
        rows_by_symbol: Dict[str, ChainSweepContract] = {row.symbol: row for row in sweep.contracts}

        # Pass 1: resolve data availability + dedup — cheap (a CSV min/max
        # scan, no backtest run), so done up front rather than inside a
        # worker, and lets skipped/missing contracts short-circuit before
        # ever touching the process pool.
        to_run: List[tuple] = []  # (symbol, csv_path, effective_date_from, effective_date_to)
        n_done = 0
        for symbol, row in rows_by_symbol.items():
            pair = by_symbol.get(symbol)
            if pair is None:
                row.status, row.error = "error", "no historical data file for this contract"
                n_done += 1
                continue

            contract, csv_path = pair
            try:
                df = load_backtest_csv(csv_path)
                df_min, df_max = df["date"].min().date(), df["date"].max().date()
            except Exception as e:  # noqa: BLE001 -- one bad file must not kill the whole sweep
                row.status, row.error = "error", str(e)
                n_done += 1
                continue
            effective_date_from = requested_date_from or df_min
            effective_date_to = requested_date_to or df_max

            candidate = BacktestRunParams(
                strategy_name=sweep.strategy_name,
                symbols=contract.symbol,
                timeframe=config.timeframe,
                date_from=effective_date_from,
                date_to=effective_date_to,
                quantity=config.quantity,
                stoploss_pct=config.stoploss_pct,
                target_pct=config.target_pct,
                trailing_pct=config.trailing_pct,
                max_cycles_per_day=config.max_cycles_per_day,
                start_time=config.start_time,
                end_time=config.end_time,
                charges_enabled=charges_enabled,
                strategy_params_json=strategy_params_json,
            )
            existing = existing_by_identity.get(candidate)
            if existing is not None:
                metrics = existing.result.get("metrics", {})
                row.status = "skipped"
                row.saved_result_id = existing.id
                row.total_trades = metrics.get("total_trades")
                row.total_pnl = metrics.get("total_pnl")
                row.win_rate = metrics.get("win_rate")
                row.profit_factor = metrics.get("profit_factor")
                n_done += 1
            else:
                row.status = "running"
                to_run.append((symbol, csv_path, effective_date_from, effective_date_to))

        sweep_repo.save(sweep)

        # Pass 2: the actual backtests. Below PARALLEL_THRESHOLD, plain
        # sequential beats a process pool -- measured, not assumed: a
        # ProcessPoolExecutor's worker-spawn cost on Windows is ~10s
        # fixed overhead (each worker cold-imports polars/sqlalchemy/etc.
        # from scratch) against each contract's own backtest costing only
        # ~0.1-0.15s, so an 87-contract sweep measured SLOWER in parallel
        # (15.0s) than sequential (11.5s). At real full-chain scale that
        # fixed cost amortizes away and wins decisively -- the same
        # 1,925-contract RELIANCE sweep measured 117s parallel vs. an
        # extrapolated ~248s sequential. ~140 contracts is the measured
        # break-even; 150 leaves a small margin. Every underlying's
        # SINGLE-expiry sweep (the default, ~80-110 contracts) stays
        # sequential; "sweep all expiries" (thousands of contracts, the
        # scenario this optimization actually targets) goes parallel.
        if to_run:
            tasks = {
                symbol: (
                    strategy_cls, symbol, csv_path, config, charge_config,
                    requested_date_from, requested_date_to, extra_indicators,
                )
                for symbol, csv_path, _, _ in to_run
            }
            date_bounds = {symbol: (dfrom, dto) for symbol, _, dfrom, dto in to_run}

            def _iter_computed():
                if len(to_run) < PARALLEL_THRESHOLD:
                    for symbol, args in tasks.items():
                        try:
                            _, trades = _run_one_contract(args)
                            yield symbol, trades, None
                        except Exception as e:  # noqa: BLE001
                            yield symbol, None, e
                else:
                    with ProcessPoolExecutor(max_workers=max_workers) as pool:
                        futures = {pool.submit(_run_one_contract, args): symbol for symbol, args in tasks.items()}
                        for future in as_completed(futures):
                            symbol = futures[future]
                            try:
                                _, trades = future.result()
                                yield symbol, trades, None
                            except Exception as e:  # noqa: BLE001
                                yield symbol, None, e

            for symbol, trades, error in _iter_computed():
                row = rows_by_symbol[symbol]
                effective_date_from, effective_date_to = date_bounds[symbol]
                if error is not None:
                    row.status, row.error = "error", str(error)
                else:
                    try:
                        saved = save_per_symbol_results(
                            result_repo,
                            strategy_name=sweep.strategy_name,
                            symbols_used=[symbol],
                            all_trades=trades,
                            config=config,
                            charges_enabled=charges_enabled,
                            date_from=effective_date_from,
                            date_to=effective_date_to,
                            capital=capital,
                            strategy_params_json=strategy_params_json,
                        )
                        result = saved[symbol]
                        metrics = result.result.get("metrics", {})
                        row.status = "done"
                        row.saved_result_id = result.id
                        row.total_trades = metrics.get("total_trades")
                        row.total_pnl = metrics.get("total_pnl")
                        row.win_rate = metrics.get("win_rate")
                        row.profit_factor = metrics.get("profit_factor")
                    except Exception as e:  # noqa: BLE001 -- one bad contract must not kill the whole sweep
                        row.status, row.error = "error", str(e)

                n_done += 1
                if n_done % SAVE_EVERY == 0 or n_done == len(sweep.contracts):
                    sweep_repo.save(sweep)

        sweep.status = "done"
        sweep.finished_at = dt.datetime.now()
        sweep_repo.save(sweep)
    except Exception as e:
        # A bug here shouldn't leave the sweep stuck showing "running"
        # forever with no explanation — surface it on the sweep itself.
        sweep.status = "failed"
        sweep.error = str(e)
        sweep.finished_at = dt.datetime.now()
        try:
            sweep_repo.save(sweep)
        except Exception:
            pass
