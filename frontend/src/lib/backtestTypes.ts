// Types for the standalone backtest API (backtest_server.py, proxied at
// /api/backtest/* — see frontend/vite.config.ts). Field names mirror the
// backend response exactly; PerformanceMetrics/StrategyBreakdown/
// EquityPoint/CandleTimeframe are the same shapes the live Performance
// tab already uses (core/domain/metrics.py doesn't care whether trades
// came from live paper trading or a backtest), reused here rather than
// redeclared.
import type { CandleTimeframe, EquityPoint, PerformanceMetrics, StrategyBreakdown, StrategyInfo } from "./types"

export type { StrategyInfo }

export interface BacktestTrade {
  symbol: string
  side: "BUY" | "SELL"
  closed_at: string // ISO datetime
  entry: number
  exit: number
  qty: number
  pnl: number
  charges: number | null
  net_pnl: number | null
  market_condition: string | null
}

export interface BacktestRunConfig {
  strategy: string
  symbols?: string[] // omit/empty -> full watchlist
  timeframe: CandleTimeframe
  quantity: number
  stoploss_pct: number
  target_pct: number
  trailing_pct: number
  max_cycles_per_day: number
  start_time: string
  end_time: string
  capital: number
  charges: boolean
  // "YYYY-MM-DD"; empty string on either end -> unbounded on that side
  // (as much history as the CSV has).
  date_from: string
  date_to: string
}

export interface BacktestRunResult {
  symbols_used: string[]
  symbols_missing_data: string[]
  total_trades: number
  trades: BacktestTrade[]
  trades_truncated: boolean
  metrics: PerformanceMetrics
  equity_curve: EquityPoint[]
  by_symbol: StrategyBreakdown[]
  by_market_condition: StrategyBreakdown[]
  by_side: StrategyBreakdown[]
  saved_result_id: number
}

export const DEFAULT_BACKTEST_CONFIG: BacktestRunConfig = {
  strategy: "",
  symbols: undefined,
  timeframe: "minute",
  quantity: 50,
  stoploss_pct: 0.8,
  target_pct: 2.0,
  trailing_pct: 0.1,
  max_cycles_per_day: 10,
  start_time: "09:20",
  end_time: "11:30",
  capital: 100_000,
  charges: true,
  date_from: "",
  date_to: "",
}

// One stored backtest_results row — every field that makes up its
// identity (see core/domain/backtest_result.py::BacktestRunParams) plus a
// flattened slice of its stored metrics, enough to drive the Analysis
// tab's dropdown and comparison chart without a second round trip.
export interface BacktestResultSummary {
  id: number
  strategy_name: string
  symbols: string // sorted comma-joined list, or "WATCHLIST"
  timeframe: string
  date_from: string
  date_to: string
  quantity: number
  stoploss_pct: number
  target_pct: number
  trailing_pct: number
  max_cycles_per_day: number
  start_time: string
  end_time: string
  charges_enabled: boolean
  total_trades: number
  win_rate: number | null
  profit_factor: number | null
  total_pnl: number | null
  sharpe_ratio: number | null
  max_drawdown_pct: number | null
  created_at: string | null
}

export interface BacktestResultDetail {
  summary: BacktestResultSummary
  // Same shape as BacktestRunResult minus `trades`/`trades_truncated` —
  // stored results never keep the raw trade log (see
  // backtest_server.py's /api/backtest/run).
  result: Omit<BacktestRunResult, "trades" | "trades_truncated" | "saved_result_id"> & {
    capital: number
  }
}
