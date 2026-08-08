// Live regime verdict for one symbol, from core/domain/regime_classification.py
// — same classifier the Market Analysis page's on-demand lookup uses, run
// here on every watchlist symbol every broadcast tick. null until the
// symbol has real values for every input (still warming up).
export interface RegimeClassification {
  regime: string
  trend_strength: string
  volatility_state: string
  confidence_score: number
  decision: string
  suggested_side: "BUY" | "SELL" | null
  summary: string
}

// Screener category membership — independent of `regime` (see
// classify_screens' per-check None guards), a symbol can be in zero, one,
// or several of these at once. Values are plain strings, not a union,
// since the category list lives server-side in regime_classification.py.
export type Screen = string

export interface SnapshotEntry {
  ltp: number | null
  ema5: number | null
  ema9: number | null
  ema21: number | null
  rsi: number | null
  adx: number | null
  atr_pct: number | null
  vwap: number | null
  volume_ratio: number | null
  orb_low: number | null
  distance_to_or_low: number | null
  regime: RegimeClassification | null
  screens: Screen[]
}

export type Snapshot = Record<string, SnapshotEntry>

export interface StageResults {
  ORB: {
    stage1: string[]
    stage2: string[]
    stage3: string[]
  }
}

export interface Position {
  side: "BUY" | "SELL"
  qty: number
  entry: number
}

export interface Trade {
  symbol: string
  entry: number
  exit: number
  side: "BUY" | "SELL"
  qty: number
  pnl: number
  // Brokerage + STT + exchange/SEBI charges + stamp duty + GST for this
  // trade's round trip (core/domain/charges.py), and pnl minus that —
  // null only for a trade closed before charges existed and never
  // backfilled.
  charges: number | null
  net_pnl: number | null
  deployment_id?: string
  strategy_name?: string
}

export interface BrokerStatus {
  available_capital: number
  open_positions: Record<string, Position>
  total_trades: number
  trade_log: Trade[]
}

export interface PositionView {
  symbol: string
  side: "BUY" | "SELL"
  qty: number
  entry: number
  ltp: number | null
  stop_loss: number | null
  target: number | null
  unrealized_pnl: number | null
  deployment_id?: string
  strategy_name?: string
}

export interface MarketTickerEntry {
  ltp: number
  prev_close: number | null
  change: number | null
  change_pct: number | null
  timestamp: string
}

export type MarketTicker = Record<string, MarketTickerEntry>

export interface LivePayload {
  snapshot: Snapshot
  stage_results: StageResults
  broker_status: BrokerStatus
  positions: PositionView[]
  market_ticker: MarketTicker
}

export interface ScreenerRow {
  symbol: string
  stage: "None" | "Stage 1" | "Stage 2" | "Stage 3"
  ltp: number | null
  ema5: number | null
  ema9: number | null
  vwap: number | null
  rsi: number | null
  volume_ratio: number | null
  atr_pct: number | null
  orb_low: number | null
  distance_to_or_low: number | null
  screens: Screen[]
}

export interface MarketAnalysis {
  symbol?: string
  time?: string
  // "YYYY-MM-DD HH:MM:SS" of the last CLOSED 1-min candle this was
  // computed from — compare Zerodha's chart at this timestamp, not "now",
  // since Zerodha's live chart also folds in the still-forming candle.
  as_of?: string
  ltp?: number
  ema5?: number | null
  ema9?: number | null
  ema21?: number | null
  rsi?: number | null
  adx?: number | null
  vwap?: number | null
  volume_ratio?: number | null
  regime?: string
  trend_strength?: string
  volatility_state?: string
  confidence_score?: number
  decision?: string
  suggested_side?: "BUY" | "SELL" | null
  summary?: string
  atr_pct?: number | null
  // Rolling win rate for this exact (symbol, decision) pair — see
  // services/market_analysis_engine.py's regime accuracy tracking. null
  // when there's no repository wired up, or the decision is NO TRADE
  // (nothing to score a win/loss against).
  accuracy?: {
    win_rate: number | null // null until n >= min_sample
    n: number
    min_sample: number
    horizon_minutes: number
    lookback_days: number
  } | null
  error?: string
}

export interface Watchlist {
  symbols: string[]
}

export interface StrategyInfo {
  name: string
  display_name: string
  side: "BUY" | "SELL"
}

export interface StrategySource {
  name: string
  source: string
}

export interface RejectedEntry {
  symbol: string
  side: "BUY" | "SELL"
  quantity: number
  price: number
  required_capital: number
  available_capital: number
  reason: string
  at: string
}

export interface DeploymentStatus {
  available_capital: number
  realized_pnl: number // net of charges — see core/domain/charges.py
  total_charges: number
  gross_realized_pnl: number // before charges, for comparison against realized_pnl
  total_trades: number
  open_position_count: number
  win_rate: number | null
  profit_factor: number | null
  gross_profit: number
  gross_loss: number
  max_drawdown: number
  max_drawdown_pct: number | null
  avg_r_multiple: number | null
  sharpe_ratio: number | null
  rejected_entries: RejectedEntry[]
}

// Bar size indicators are computed on for this deployment — every value
// is derived by resampling the same 1-minute base data server-side, not
// fetched separately. Must match live/live_engine.py::SUPPORTED_TIMEFRAMES.
// Named distinctly from the analytics dashboard's own `Timeframe` (below,
// "daily"/"weekly"/"monthly" chart bucketing) — same word, different axis.
export type CandleTimeframe =
  | "minute"
  | "3minute"
  | "5minute"
  | "10minute"
  | "15minute"
  | "30minute"

export interface Deployment {
  id: string
  strategy_name: string
  symbols: string[]
  capital: number
  quantity: number
  stoploss_pct: number
  target_pct: number
  trailing_pct: number
  max_cycles_per_day: number
  enabled: boolean
  start_time: string // "HH:MM", 24h — active window for entries + exit management
  end_time: string // "HH:MM", 24h
  timeframe: CandleTimeframe
  running: boolean
  status: DeploymentStatus | null
}

export interface DeploymentInput {
  strategy_name: string
  symbols: string[]
  capital: number
  quantity: number
  stoploss_pct: number
  target_pct: number
  trailing_pct: number
  max_cycles_per_day: number
  enabled: boolean
  start_time: string
  end_time: string
  timeframe: CandleTimeframe
}

// ---------------------------------------------------------------------
// Performance analytics — field names mirror core/domain/metrics.py and
// server/main.py's /api/analytics/summary response exactly. Every number
// here is computed server-side; components only format/display, never
// recompute.
// ---------------------------------------------------------------------

export interface PerformanceMetrics {
  total_trades: number
  winning_trades: number
  losing_trades: number
  win_rate: number | null
  profit_factor: number | null
  gross_profit: number
  gross_loss: number
  total_pnl: number // net of charges — "realized profit"
  total_charges: number
  gross_total_pnl: number // before charges, for comparison against total_pnl
  avg_win: number | null
  avg_loss: number | null
  max_drawdown: number
  max_drawdown_pct: number | null
  avg_r_multiple: number | null
  sharpe_ratio: number | null
}

// The editable brokerage/tax rate card — field names mirror
// core/domain/charges.py::ChargeConfig exactly. Every *_pct is a fraction
// (0.0003, not 0.03), matching the backend convention.
export interface ChargeConfig {
  brokerage_pct: number
  brokerage_max_per_order: number
  stt_pct: number
  exchange_txn_pct: number
  sebi_pct: number
  stamp_duty_pct: number
  gst_pct: number
}

export interface StrategyBreakdown {
  strategy_name: string
  deployment_id: string | null
  capital: number
  metrics: PerformanceMetrics
}

export interface EquityPoint {
  bucket: string // ISO date
  cumulative_pnl: number
}

export interface PeriodPnl {
  bucket: string // ISO date
  pnl: number
}

export interface DrawdownPoint {
  closed_at: string // ISO datetime
  drawdown: number
  drawdown_pct: number | null
}

export interface HistogramBucket {
  range_start: number
  range_end: number
  count: number
}

export interface RollingSharpePoint {
  date: string // ISO date
  sharpe_ratio: number | null
}

export type Timeframe = "daily" | "weekly" | "monthly"

export interface AnalyticsFilters {
  strategy?: string
  symbol?: string
  date_from?: string // ISO date
  date_to?: string // ISO date
  timeframe: Timeframe
}

// Capital-independent subset of PerformanceMetrics — a (strategy, symbol)
// or (strategy, market_condition) bucket has no capital pool of its own,
// so drawdown_pct/sharpe aren't included (see core/domain/metrics.py's
// HeatmapCell).
export interface HeatmapCellData {
  total_trades: number
  win_rate: number | null
  profit_factor: number | null
  total_pnl: number
  avg_r_multiple: number | null
}

export interface HeatmapRow {
  row: string // strategy_name
  column: string // symbol, or market_condition label
  cell: HeatmapCellData
}

// One point per (strategy, bucket) — cumulative_pnl accumulates within
// that strategy's own series only, not across strategies (see
// core/domain/metrics.py::strategy_trend).
export interface StrategyTrendPoint {
  strategy_name: string
  bucket: string // ISO date
  trades: number
  win_rate: number | null
  profit_factor: number | null
  cumulative_pnl: number
}

// Pearson correlation of daily P&L between a pair of strategies. One row
// per unique pair (alphabetically ordered a/b, no A×B + B×A duplicates).
export interface CorrelationPair {
  strategy_a: string
  strategy_b: string
  correlation: number | null
}

export interface AnalyticsSummary {
  overall: PerformanceMetrics
  by_strategy: StrategyBreakdown[]
  equity_curve: EquityPoint[]
  pnl_by_period: PeriodPnl[]
  drawdown: DrawdownPoint[]
  profit_distribution: HistogramBucket[]
  rolling_sharpe: RollingSharpePoint[]
  heatmap_strategy_symbol: HeatmapRow[]
  heatmap_strategy_condition: HeatmapRow[]
  strategy_trend: StrategyTrendPoint[]
  strategy_correlation: CorrelationPair[]
  available_strategies: string[]
  available_symbols: string[]
}
