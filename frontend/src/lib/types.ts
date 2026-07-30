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
  realized_pnl: number
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
  total_pnl: number
  avg_win: number | null
  avg_loss: number | null
  max_drawdown: number
  max_drawdown_pct: number | null
  avg_r_multiple: number | null
  sharpe_ratio: number | null
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

export interface AnalyticsSummary {
  overall: PerformanceMetrics
  by_strategy: StrategyBreakdown[]
  equity_curve: EquityPoint[]
  pnl_by_period: PeriodPnl[]
  drawdown: DrawdownPoint[]
  profit_distribution: HistogramBucket[]
  rolling_sharpe: RollingSharpePoint[]
  available_strategies: string[]
  available_symbols: string[]
}
