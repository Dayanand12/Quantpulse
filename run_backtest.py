# run_backtest.py
"""CLI for runners/backtesting/ — a single backtest, or a parameter sweep,
without writing a Python script each time.

Examples:
    python run_backtest.py --symbol RELIANCE --strategy orb_reversal
    python run_backtest.py --symbol ABB --strategy orb_reversal --timeframe 5minute --charges
    python run_backtest.py --symbol RELIANCE,TCS,INFY --strategy vwap_reclaim
    python run_backtest.py --watchlist --strategy vwap_reclaim --charges
    python run_backtest.py --symbol ABB --strategy orb_reversal --sweep \
        --stoploss 0.5,0.8,1.2 --target 1.5,2.0,2.5 --rank-by total_pnl
    python run_backtest.py --symbol ABB --strategy orb_reversal --out trades.csv
"""

import argparse
import datetime as dt
import os
import sys
from typing import List, Optional, Tuple

import polars as pl

from dataclasses import asdict

from core.domain.charges import ChargeConfig
from core.domain.metrics import PerformanceMetrics, compute_performance_metrics, equity_curve
from core.domain.models import StrategyConfig
from infrastructure.config.settings import get_settings
from infrastructure.persistence.database import create_session_factory
from infrastructure.persistence.sql_backtest_result_repository import SqlBacktestResultRepository
from runners.backtesting.engine import run_backtest
from runners.backtesting.historical_loader import load_equity_csv
from runners.backtesting.parameter_sweep import build_config_grid, rank_by, sweep_parameters
from runners.backtesting.report import write_backtest_report, write_sweep_report
from runners.backtesting.result_persistence import (
    breakdown_rows,
    required_dynamic_indicators,
    save_backtest_result,
    symbols_identity,
)
from runners.backtesting.strategy_resolver import UnknownStrategyError, resolve_strategy_class
from runners.backtesting.watchlist import get_tradeable_watchlist_symbols

DEFAULT_REPORT_DIR = "reports/backtests"


def _default_csv_path(symbol: str) -> str:
    return os.path.join(get_settings().historical_data_dir, f"{symbol}_historical.csv")


def _parse_floats(value: str) -> list:
    return [float(v) for v in value.split(",")]


def _resolve_symbols(args) -> List[str]:
    if args.watchlist:
        return get_tradeable_watchlist_symbols()
    return [s.strip() for s in args.symbol.split(",") if s.strip()]


def _csv_date_bounds(path: str) -> Tuple[dt.date, dt.date]:
    """Cheap min/max of a CSV's date column without a full load+timezone
    conversion — only used to fill in the stored identity's date bounds
    when --date-from/--date-to weren't given (sweep mode loads full data
    per worker process, not here, so this avoids doubling that I/O)."""
    row = (
        pl.scan_csv(path, try_parse_dates=True)
        .select(pl.col("date").min().alias("min"), pl.col("date").max().alias("max"))
        .collect()
        .row(0, named=True)
    )
    return row["min"].date(), row["max"].date()


def _report_label(symbols: List[str]) -> str:
    if len(symbols) == 1:
        return symbols[0]
    if len(symbols) <= 3:
        return "+".join(symbols)
    return f"{'+'.join(symbols[:3])}+{len(symbols) - 3}more"


def _print_metrics(m: PerformanceMetrics) -> None:
    print(f"  Trades:         {m.total_trades} ({m.winning_trades} win / {m.losing_trades} loss)")
    print(f"  Win rate:       {m.win_rate:.1f}%" if m.win_rate is not None else "  Win rate:       N/A")
    print(f"  Profit factor:  {m.profit_factor:.2f}" if m.profit_factor is not None else "  Profit factor:  N/A")
    print(f"  Gross P&L:      {m.gross_total_pnl:,.2f}")
    print(f"  Charges:        {m.total_charges:,.2f}")
    print(f"  Net P&L:        {m.total_pnl:,.2f}")
    print(f"  Max drawdown:   {m.max_drawdown:,.2f}")
    print(f"  Sharpe:         {m.sharpe_ratio:.2f}" if m.sharpe_ratio is not None else "  Sharpe:         N/A")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbol", help="e.g. RELIANCE, or RELIANCE,TCS,INFY for multiple. Required unless --watchlist.")
    parser.add_argument(
        "--watchlist", action="store_true",
        help="run every tradeable symbol in the live watchlist instead of --symbol (aggregated into one result)",
    )
    parser.add_argument("--strategy", required=True, help="strategy name, e.g. orb_reversal")
    parser.add_argument("--csv", help="defaults to <historical_data_dir>/{symbol}_historical.csv (single-symbol runs only)")
    parser.add_argument("--capital", type=float, default=100_000)
    parser.add_argument("--timeframe", default="minute", choices=[
        "minute", "3minute", "5minute", "10minute", "15minute", "30minute",
    ])
    parser.add_argument("--quantity", type=int, default=50)
    parser.add_argument("--stoploss", default="0.8", help="single value, or comma-separated for --sweep")
    parser.add_argument("--target", default="2.0", help="single value, or comma-separated for --sweep")
    parser.add_argument("--trailing", default="0.1", help="single value, or comma-separated for --sweep")
    parser.add_argument("--max-cycles", type=int, default=10)
    parser.add_argument("--start-time", default="09:20")
    parser.add_argument("--end-time", default="11:30")
    parser.add_argument("--charges", action="store_true", help="apply Zerodha-realistic charges (net P&L)")
    parser.add_argument("--date-from", help="YYYY-MM-DD; omit for as much history as the CSV has")
    parser.add_argument("--date-to", help="YYYY-MM-DD; omit for as much history as the CSV has")
    parser.add_argument("--sweep", action="store_true", help="run every combination of --stoploss/--target/--trailing")
    parser.add_argument("--rank-by", default="total_pnl", help="PerformanceMetrics field to sort sweep results by")
    parser.add_argument("--top", type=int, default=10, help="how many sweep results to print")
    parser.add_argument("--out", help="also write the raw trade log to this CSV path (single-run mode only)")
    parser.add_argument(
        "--no-report", action="store_true",
        help=f"skip writing the Excel report (written to {DEFAULT_REPORT_DIR}/ by default)",
    )
    parser.add_argument("--report-dir", default=DEFAULT_REPORT_DIR)
    parser.add_argument(
        "--no-save", action="store_true",
        help="skip logging this run to the backtest_results table (still writes the Excel report)",
    )
    args = parser.parse_args()

    if not args.watchlist and not args.symbol:
        print("Either --symbol or --watchlist is required.", file=sys.stderr)
        sys.exit(1)
    if args.csv and (args.watchlist or "," in (args.symbol or "")):
        print("--csv only applies to a single --symbol.", file=sys.stderr)
        sys.exit(1)

    symbols = _resolve_symbols(args)
    label = _report_label(symbols)
    charge_config = ChargeConfig() if args.charges else None
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    requested_date_from = dt.date.fromisoformat(args.date_from) if args.date_from else None
    requested_date_to = dt.date.fromisoformat(args.date_to) if args.date_to else None
    symbols_id = symbols_identity(symbols, is_full_watchlist=args.watchlist)

    try:
        strategy_cls = resolve_strategy_class(args.strategy)
    except UnknownStrategyError as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    extra_indicators = required_dynamic_indicators(args.strategy)

    base_config = StrategyConfig(
        quantity=args.quantity,
        stoploss_pct=_parse_floats(args.stoploss)[0],
        target_pct=_parse_floats(args.target)[0],
        trailing_pct=_parse_floats(args.trailing)[0],
        max_cycles_per_day=args.max_cycles,
        start_time=args.start_time,
        end_time=args.end_time,
        timeframe=args.timeframe,
    )

    symbol_csv_pairs = [(s, args.csv or _default_csv_path(s)) for s in symbols]
    missing = [(s, p) for s, p in symbol_csv_pairs if not os.path.exists(p)]
    if missing:
        for s, p in missing:
            print(f"No historical data for {s}: {p} not found", file=sys.stderr)
        symbol_csv_pairs = [(s, p) for s, p in symbol_csv_pairs if (s, p) not in missing]
        if not symbol_csv_pairs:
            sys.exit(1)

    if args.sweep:
        grid = build_config_grid(
            base_config,
            stoploss_pct=_parse_floats(args.stoploss),
            target_pct=_parse_floats(args.target),
            trailing_pct=_parse_floats(args.trailing),
        )
        print(f"Sweeping {len(grid)} config combinations for {args.strategy} on {label} "
              f"({len(symbol_csv_pairs)} symbol(s))...")
        results = sweep_parameters(
            strategy_cls, symbol_csv_pairs, grid, args.capital, charge_config,
            date_from=requested_date_from, date_to=requested_date_to,
            extra_indicators=extra_indicators,
        )
        ranked = rank_by(results, args.rank_by)

        print(f"\nTop {min(args.top, len(ranked))} by {args.rank_by}:\n")
        for r in ranked[: args.top]:
            c = r.config
            value = getattr(r.metrics, args.rank_by)
            value_str = f"{value:,.2f}" if isinstance(value, float) else str(value)
            print(
                f"  sl={c.stoploss_pct:<5} tp={c.target_pct:<5} trail={c.trailing_pct:<5} "
                f"-> trades={r.metrics.total_trades:<4} {args.rank_by}={value_str}"
            )

        if not args.no_report:
            path = os.path.join(args.report_dir, f"{label}_{args.strategy}_sweep_{timestamp}.xlsx")
            write_sweep_report(ranked, label, args.strategy, path)
            print(f"\nReport (every config, ranked): {path}")

        if not args.no_save:
            data_min = data_max = None
            for _, csv_path in symbol_csv_pairs:
                lo, hi = _csv_date_bounds(csv_path)
                data_min = lo if data_min is None else min(data_min, lo)
                data_max = hi if data_max is None else max(data_max, hi)

            session_factory = create_session_factory(get_settings().database_url)
            result_repo = SqlBacktestResultRepository(session_factory)
            for r in results:
                save_backtest_result(
                    result_repo, strategy_name=args.strategy, symbols_id=symbols_id,
                    config=r.config, charges_enabled=args.charges,
                    date_from=requested_date_from or data_min, date_to=requested_date_to or data_max,
                    result={
                        "total_trades": r.metrics.total_trades,
                        "metrics": asdict(r.metrics),
                        "capital": args.capital,
                        # sweep_parameters() only returns aggregated
                        # metrics per config, not the raw trades (would
                        # mean shipping trade objects back through every
                        # worker process for every config combination) —
                        # so these stay empty rather than absent, keeping
                        # the shape consistent with every other saved
                        # result the Analysis tab renders.
                        "symbols_used": [],
                        "equity_curve": [],
                        "by_symbol": [],
                        "by_market_condition": [],
                        "by_side": [],
                    },
                )
            print(f"\nLogged {len(results)} config result(s) to backtest_results.")
        return

    print(f"Backtesting {args.strategy} on {label} ({len(symbol_csv_pairs)} symbol(s)), timeframe={args.timeframe}...")
    all_trades = []
    per_symbol_counts = []
    data_min: Optional[dt.date] = None
    data_max: Optional[dt.date] = None
    for symbol, csv_path in symbol_csv_pairs:
        df = load_equity_csv(csv_path)
        df_min, df_max = df["date"].min().date(), df["date"].max().date()
        data_min = df_min if data_min is None else min(data_min, df_min)
        data_max = df_max if data_max is None else max(data_max, df_max)

        strategy_instance = strategy_cls()  # fresh instance per symbol — no stale per-symbol state carried over
        trades = run_backtest(
            strategy_instance, symbol, df, base_config, charge_config=charge_config,
            date_from=requested_date_from, date_to=requested_date_to,
            extra_indicators=extra_indicators,
        )
        all_trades.extend(trades)
        per_symbol_counts.append((symbol, len(trades)))

    metrics = compute_performance_metrics(all_trades, args.capital)

    print(f"\n{label} / {args.strategy} - {len(all_trades)} trades\n")
    if len(symbol_csv_pairs) > 1:
        active = [f"{s}:{n}" for s, n in per_symbol_counts if n > 0]
        print(f"  By symbol: {', '.join(active) if active else '(none fired)'}\n")
    _print_metrics(metrics)

    if args.out and all_trades:
        import polars as pl
        pl.DataFrame([{
            "symbol": t.symbol, "closed_at": t.closed_at, "side": t.side.value, "entry": t.entry_price,
            "exit": t.exit_price, "qty": t.quantity, "pnl": t.pnl,
            "charges": t.charges, "net_pnl": t.net_pnl, "market_condition": t.market_condition,
        } for t in all_trades]).write_csv(args.out)
        print(f"\nRaw trade CSV written to {args.out}")

    if not args.no_report:
        path = os.path.join(args.report_dir, f"{label}_{args.strategy}_{timestamp}.xlsx")
        write_backtest_report(all_trades, label, args.strategy, args.capital, path)
        print(f"\nReport: {path}")

    if not args.no_save:
        session_factory = create_session_factory(get_settings().database_url)
        result_repo = SqlBacktestResultRepository(session_factory)
        saved = save_backtest_result(
            result_repo, strategy_name=args.strategy, symbols_id=symbols_id,
            config=base_config, charges_enabled=args.charges,
            date_from=requested_date_from or data_min, date_to=requested_date_to or data_max,
            result={
                "symbols_used": [s for s, _ in per_symbol_counts],
                "total_trades": len(all_trades),
                "metrics": asdict(metrics),
                "equity_curve": [asdict(p) for p in equity_curve(all_trades)],
                # Same shape backtest_server.py's /api/backtest/run saves —
                # the Analysis tab's StrategyTable expects these three to
                # exist regardless of which path produced the result.
                "by_symbol": breakdown_rows(all_trades, lambda t: t.symbol),
                "by_market_condition": breakdown_rows(all_trades, lambda t: t.market_condition),
                "by_side": breakdown_rows(all_trades, lambda t: t.side.value),
                "capital": args.capital,
            },
        )
        print(f"\nLogged to backtest_results (id={saved.id}).")


if __name__ == "__main__":
    main()
