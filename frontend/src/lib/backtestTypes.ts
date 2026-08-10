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
  // Raw strategies/<name>.json content active for this run (see
  // core/domain/strategy_conditions.py) — "" for a strategy not migrated
  // to condition-JSON yet.
  strategy_params_json: string
  total_trades: number
  win_rate: number | null
  profit_factor: number | null
  total_pnl: number | null
  sharpe_ratio: number | null
  max_drawdown_pct: number | null
  created_at: string | null
}

// Compact "adx_threshold=25, volume_ratio_threshold=1.5" summary of a
// stored result's indicator parameters, for dropdown labels/tooltips —
// "" if the strategy has no params file or the JSON's `parameters` block
// is empty (e.g. ema_crossover, which has no named parameters at all).
export function formatStrategyParams(rawJson: string): string {
  if (!rawJson) return ""
  try {
    const parsed = JSON.parse(rawJson) as { parameters?: Record<string, number> }
    const params = parsed.parameters
    if (!params || Object.keys(params).length === 0) return ""
    return Object.entries(params)
      .map(([key, value]) => `${key}=${value}`)
      .join(", ")
  } catch {
    return ""
  }
}

// The "6 panels" batch feature: one strategy, several parameter-override
// sets, run together in one request (backtest_server.py's
// /api/backtest/run-batch, runners/backtesting/batch_runner.py). Every
// field except `panels` mirrors BacktestRunConfig — the same symbols/
// dates/risk config apply to every panel, only each panel's `overrides`
// differs.
export interface BatchPanelConfig {
  label: string
  overrides: Record<string, number>
}

export interface BatchRunConfig {
  strategy: string
  panels: BatchPanelConfig[]
  symbols?: string[]
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
  date_from: string
  date_to: string
  save: boolean
}

export interface BatchPanelResult {
  label: string
  overrides: Record<string, number>
  strategy_params_json: string
  total_trades: number
  metrics: PerformanceMetrics
  equity_curve: EquityPoint[]
  by_symbol: StrategyBreakdown[]
  by_market_condition: StrategyBreakdown[]
  by_side: StrategyBreakdown[]
  saved_result_id?: number
}

export interface BatchRunResponse {
  symbols_used: string[]
  symbols_missing_data: string[]
  panels: BatchPanelResult[]
}

// The bulk-upload feature: an Excel of parameter scenarios processed in
// the background (backtest_server.py's POST /api/backtest/batch-jobs,
// runners/backtesting/batch_job_runner.py) — distinct from BatchRunConfig
// above (the synchronous "6 panels" feature): no panel cap, and detached
// from the request that started it, so it keeps running even if you close
// the browser entirely. `shared_config` mirrors BacktestRunConfig's
// symbols/dates/risk fields but as a loose record — it's read-only
// display data here, not something this page edits.
// "skipped": an identical result already existed (same strategy, symbols,
// dates, resolved risk/sizing, and resolved parameters) — nothing ran,
// saved_result_id points at the pre-existing row. See runners/
// backtesting/batch_job_runner.py::_find_already_tested.
export type BatchJobScenarioStatus = "pending" | "running" | "done" | "skipped" | "invalid" | "error"
export type BatchJobStatus = "pending" | "running" | "done" | "failed"

export interface BatchJobScenario {
  label: string
  overrides: Record<string, number>
  // This row's own risk/sizing values (Stop Loss %, Timeframe, ...) —
  // only the fields the row actually specified; anything absent falls
  // back to the job's shared_config. See runners/backtesting/
  // batch_job_runner.py::DEFAULT_SCENARIO_SETTINGS.
  config_overrides: Record<string, unknown>
  status: BatchJobScenarioStatus
  saved_result_id: number | null
  error: string | null
}

export interface BatchJob {
  id: number
  strategy_name: string
  status: BatchJobStatus
  shared_config: Record<string, unknown>
  total_scenarios: number
  processed_scenarios: number
  scenarios: BatchJobScenario[]
  error: string | null
  created_at: string | null
  finished_at: string | null
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
