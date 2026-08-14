# runners/backtesting/batch_job_runner.py
"""Processes one BatchJob's pending scenarios to completion — meant to run
in a background thread (see backtest_server.py's upload endpoint), fully
detached from whichever HTTP request started it, so it keeps going
regardless of what the browser does afterward (close the tab, close the
laptop, doesn't matter — only the backtest_server.py process itself needs
to keep running).

Every risk/sizing setting AND the date range (timeframe, stoploss_pct,
date_from, date_to, ...) is resolved PER SCENARIO from job.shared_config
overridden by that scenario's own config_overrides (see core/domain/
batch_job.py) — not one shared StrategyConfig/date range for the whole
job. This is what makes "one row per year" work: same strategy, same
parameters, a different Date From/Date To on each row. Scenarios that
resolve to IDENTICAL settings (including date range) are grouped and
still run together through runners/backtesting/batch_runner.py's
run_batch_backtests in chunks of BATCH_JOB_CHUNK_SIZE (the exact same
code path the synchronous "6 panels" feature uses) — that's this job's
version of the 6-panel feature's parallelism; a scenario with genuinely
different settings just can't share a batch call with one that has
different ones, since run_batch_backtests takes a single StrategyConfig
and date range per call. Symbols are the one thing that stays job-level,
not per-row — mixing different symbol sets per scenario would break the
"resolve available data once" step below.

Progress (job_repo.save) and each chunk's results (result_repo, one row
per scenario) are persisted after every chunk rather than all at the end.
A scenario that fails (a chunk-level exception, or one panel's own result
assembly failing) is marked "error" and the job moves on — one bad
scenario should never take down the rest.

Before any of that, every pending scenario is checked against
backtest_results for an EXISTING row with an identical identity (same
strategy, symbols, dates, resolved risk/sizing, and resolved
conditions.json parameters) — see _find_already_tested(). A match means
"skipped," not "done": nothing runs, the scenario just points at the
existing result. This is what makes "export my results, add a few new
rows, re-upload the whole file" only spend time on the genuinely new
rows instead of recomputing everything that was already tested.
"""

import datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type

from core.application.interfaces.backtest_result_repository import IBacktestResultRepository
from core.application.interfaces.batch_job_repository import IBatchJobRepository
from core.application.interfaces.strategy import IStrategy
from core.domain.backtest_result import BacktestRunParams
from core.domain.batch_job import BatchJob, BatchJobScenario
from core.domain.charges import ChargeConfig
from core.domain.models import StrategyConfig
from runners.backtesting.batch_runner import PanelSpec, merge_condition_overrides, run_batch_backtests
from runners.backtesting.historical_loader import load_backtest_csv
from runners.backtesting.result_persistence import save_per_symbol_results

BATCH_JOB_CHUNK_SIZE = 6

DEFAULT_SCENARIO_SETTINGS: Dict[str, Any] = {
    "timeframe": "minute", "quantity": 50, "stoploss_pct": 0.8, "target_pct": 2.0,
    "trailing_pct": 0.1, "max_cycles_per_day": 10, "start_time": "09:20",
    "end_time": "11:30", "capital": 100_000, "charges": True,
    # None (not a real default) means "unbounded — use however much
    # history the CSV has," same as leaving both blank on the form.
    "date_from": None, "date_to": None,
}

# Fields that determine which run_batch_backtests call a scenario can
# share — capital is deliberately excluded: it only rescales a scenario's
# OWN metrics when saved, it never changes which trades a backtest
# produces (same reasoning as core/domain/backtest_result.py's
# BacktestRunParams excluding it from the dedup identity).
_GROUPING_FIELDS = (
    "timeframe", "quantity", "stoploss_pct", "target_pct", "trailing_pct",
    "max_cycles_per_day", "start_time", "end_time", "charges", "date_from", "date_to",
)


def _parse_date(value: Optional[str]) -> Optional[dt.date]:
    return dt.date.fromisoformat(value) if value else None


def _resolve_scenario_settings(shared_config: Dict[str, Any], scenario: BatchJobScenario) -> Dict[str, Any]:
    """A scenario's blank config cell means "use the job's shared
    setting" (see core/domain/batch_job.py::BatchJobScenario.
    config_overrides) — shared_config itself falls back to
    DEFAULT_SCENARIO_SETTINGS for anything the upload form didn't send."""
    return {**DEFAULT_SCENARIO_SETTINGS, **shared_config, **scenario.config_overrides}


def _resolve_scenario_dates(
    settings: Dict[str, Any], data_min_date: Optional[dt.date], data_max_date: Optional[dt.date],
) -> Tuple[Optional[dt.date], Optional[dt.date], Optional[dt.date], Optional[dt.date]]:
    """Returns (requested_date_from, requested_date_to, effective_date_from,
    effective_date_to). requested_* (possibly both None) is what filters
    which bars run_batch_backtests actually replays. effective_* is what
    save_backtest_result's identity uses — same reasoning as
    backtest_server.py's single-run endpoint: an unbounded range still
    needs a concrete identity, so it falls back to the full span of
    whatever historical data actually exists rather than staying NULL."""
    requested_date_from = _parse_date(settings["date_from"])
    requested_date_to = _parse_date(settings["date_to"])
    effective_date_from = requested_date_from or data_min_date
    effective_date_to = requested_date_to or data_max_date
    return requested_date_from, requested_date_to, effective_date_from, effective_date_to


def _find_already_tested(
    result_repo: IBacktestResultRepository,
    strategy_name: str,
    symbols: List[str],
    data_min_date: Optional[dt.date],
    data_max_date: Optional[dt.date],
    pending: List[BatchJobScenario],
    shared_config: Dict[str, Any],
) -> List[Tuple[BatchJobScenario, Dict[str, Any]]]:
    """Returns only the scenarios that still need to run. Results are
    stored per-symbol (see save_per_symbol_results), so a scenario counts
    as "already tested" only when EVERY one of its symbols already has a
    matching stored row for its OWN resolved identity — not one combined
    identity for the whole symbol set. This is what makes dedup correctly
    granular: adding one new symbol to a watchlist and re-uploading the
    same scenarios only computes that new symbol, since every other
    symbol already matches. A scenario missing even one symbol still
    fully re-runs (this doesn't attempt partial-symbol runs) — its save
    step upserts every symbol's row regardless, so already-correct rows
    for the OTHER symbols are just harmlessly overwritten with identical
    numbers, not duplicated.

    Marked "skipped" IN PLACE (saved_result_id pointed at one matching
    row, for reference) and excluded from the return value; the caller is
    responsible for persisting those status changes. One list_results()
    call up front (a strategy's whole tuning history) rather than a query
    per scenario."""
    existing_by_identity: Dict[BacktestRunParams, int] = {
        r.params: r.id for r in result_repo.list_results(strategy_name)
    }

    to_run: List[Tuple[BatchJobScenario, Dict[str, Any]]] = []
    for scenario in pending:
        settings = _resolve_scenario_settings(shared_config, scenario)
        try:
            _, merged_params_json = merge_condition_overrides(strategy_name, scenario.overrides)
        except Exception as e:
            scenario.status, scenario.error = "error", str(e)
            continue

        _, _, effective_date_from, effective_date_to = _resolve_scenario_dates(
            settings, data_min_date, data_max_date
        )

        matched_ids: List[int] = []
        for symbol in symbols:
            candidate = BacktestRunParams(
                strategy_name=strategy_name,
                symbols=symbol,
                timeframe=settings["timeframe"],
                date_from=effective_date_from,
                date_to=effective_date_to,
                quantity=settings["quantity"],
                stoploss_pct=settings["stoploss_pct"],
                target_pct=settings["target_pct"],
                trailing_pct=settings["trailing_pct"],
                max_cycles_per_day=settings["max_cycles_per_day"],
                start_time=settings["start_time"],
                end_time=settings["end_time"],
                charges_enabled=bool(settings["charges"]),
                strategy_params_json=merged_params_json,
            )
            existing_id = existing_by_identity.get(candidate)
            if existing_id is None:
                matched_ids = []
                break
            matched_ids.append(existing_id)

        if matched_ids:
            scenario.status = "skipped"
            scenario.saved_result_id = matched_ids[0]
        else:
            to_run.append((scenario, settings))

    return to_run


def _strategy_config_from_settings(settings: Dict[str, Any]) -> StrategyConfig:
    return StrategyConfig(
        quantity=settings["quantity"],
        stoploss_pct=settings["stoploss_pct"],
        target_pct=settings["target_pct"],
        trailing_pct=settings["trailing_pct"],
        max_cycles_per_day=settings["max_cycles_per_day"],
        start_time=settings["start_time"],
        end_time=settings["end_time"],
        timeframe=settings["timeframe"],
    )


def run_batch_job(
    job: BatchJob,
    strategy_cls: Type[IStrategy],
    symbols: List[Tuple[str, str]],
    job_repo: IBatchJobRepository,
    result_repo: IBacktestResultRepository,
) -> None:
    try:
        job.status = "running"
        job_repo.save(job)

        # Resolved once up front, shared by every scenario — symbols stay
        # job-level (not per-row, unlike the risk/sizing/date-range
        # fields), so which CSVs exist and what span of history they cover
        # is a property of the job, not of any one scenario's settings.
        data_min_date: Optional[dt.date] = None
        data_max_date: Optional[dt.date] = None
        valid_symbols: List[Tuple[str, str]] = []
        for symbol, csv_path in symbols:
            if not Path(csv_path).exists():
                continue
            valid_symbols.append((symbol, csv_path))
            df = load_backtest_csv(csv_path)
            df_min = df["date"].min().date()
            df_max = df["date"].max().date()
            data_min_date = df_min if data_min_date is None else min(data_min_date, df_min)
            data_max_date = df_max if data_max_date is None else max(data_max_date, df_max)

        if not valid_symbols:
            job.status = "failed"
            job.error = "No historical data found for any requested symbol."
            job.finished_at = dt.datetime.now()
            job_repo.save(job)
            return

        pending = [s for s in job.scenarios if s.status == "pending"]

        # Skip anything that already has an identical stored result before
        # touching any of the actually-expensive work below.
        to_run = _find_already_tested(
            result_repo, job.strategy_name, [s for s, _ in valid_symbols],
            data_min_date, data_max_date, pending, job.shared_config,
        )
        job_repo.save(job)

        # Group by resolved risk/sizing/date-range settings so scenarios
        # that share them still run together in one run_batch_backtests
        # call — a scenario with genuinely different settings (e.g. a
        # different Date From/Date To) just starts its own group instead.
        groups: "Dict[tuple, List[Tuple[BatchJobScenario, Dict[str, Any]]]]" = {}
        for scenario, settings in to_run:
            key = tuple(settings[f] for f in _GROUPING_FIELDS)
            groups.setdefault(key, []).append((scenario, settings))

        for group in groups.values():
            group_settings = group[0][1]
            config = _strategy_config_from_settings(group_settings)
            charges_enabled = bool(group_settings["charges"])
            charge_config = ChargeConfig() if charges_enabled else None
            requested_date_from, requested_date_to, effective_date_from, effective_date_to = (
                _resolve_scenario_dates(group_settings, data_min_date, data_max_date)
            )

            for chunk_start in range(0, len(group), BATCH_JOB_CHUNK_SIZE):
                chunk = group[chunk_start:chunk_start + BATCH_JOB_CHUNK_SIZE]
                chunk_scenarios = [s for s, _ in chunk]
                for scenario in chunk_scenarios:
                    scenario.status = "running"
                job_repo.save(job)

                panel_specs = [PanelSpec(label=s.label, overrides=s.overrides) for s in chunk_scenarios]
                try:
                    panel_results, symbols_used, symbols_missing_data = run_batch_backtests(
                        strategy_cls, job.strategy_name, panel_specs, valid_symbols, config,
                        charge_config=charge_config, date_from=requested_date_from, date_to=requested_date_to,
                    )
                except Exception as e:
                    for scenario in chunk_scenarios:
                        scenario.status, scenario.error = "error", str(e)
                    job_repo.save(job)
                    continue

                for (scenario, settings), panel in zip(chunk, panel_results):
                    try:
                        capital = settings["capital"]
                        # One row per symbol, not one combined row — see
                        # save_per_symbol_results's docstring.
                        saved = save_per_symbol_results(
                            result_repo,
                            strategy_name=job.strategy_name,
                            symbols_used=symbols_used,
                            all_trades=panel.trades,
                            config=config,
                            charges_enabled=charges_enabled,
                            date_from=effective_date_from,
                            date_to=effective_date_to,
                            capital=capital,
                            strategy_params_json=panel.strategy_params_json,
                        )
                        scenario.status = "done"
                        # Representative pointer only (one of possibly many
                        # symbols saved this pass) — the Analysis tab's
                        # filters are the real way to browse per-symbol
                        # results going forward, not this single id.
                        scenario.saved_result_id = next(iter(saved.values())).id
                    except Exception as e:
                        scenario.status, scenario.error = "error", str(e)

                job_repo.save(job)

        job.status = "done"
        job.finished_at = dt.datetime.now()
        job_repo.save(job)
    except Exception as e:
        # A bug here shouldn't leave the job stuck showing "running"
        # forever with no explanation — surface it on the job itself.
        job.status = "failed"
        job.error = str(e)
        job.finished_at = dt.datetime.now()
        try:
            job_repo.save(job)
        except Exception:
            pass
