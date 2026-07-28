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
  time?: string
  regime?: string
  trend_strength?: string
  volatility_state?: string
  confidence_score?: number
  decision?: string
  atr_pct?: number
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
}

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
}
