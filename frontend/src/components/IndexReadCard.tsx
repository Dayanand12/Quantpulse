import { fmtNumber } from "../lib/format"
import type { MarketAnalysis as MarketAnalysisData } from "../lib/types"

const REGIME_COLOR: Record<string, string> = {
  "Bullish Trend": "var(--status-good)",
  "Bearish Trend": "var(--status-critical)",
  Range: "var(--ink-muted)",
  Transition: "var(--status-warning)",
}

const SIDE_COLOR: Record<string, string> = {
  BUY: "var(--status-good)",
  SELL: "var(--status-critical)",
}

interface IndexReadCardProps {
  symbol: string
  data: MarketAnalysisData | null
}

export function IndexReadCard({ symbol, data }: IndexReadCardProps) {
  if (!data || data.error) {
    return (
      <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5">
        <div className="text-sm font-medium">{symbol}</div>
        <p className="mt-2 text-xs text-[var(--ink-muted)]">{data?.error ?? "Loading…"}</p>
      </div>
    )
  }

  const sideColor = data.suggested_side ? SIDE_COLOR[data.suggested_side] : undefined

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium">{symbol}</div>
        {data.suggested_side && (
          <span
            className="rounded-full px-2 py-0.5 text-xs font-semibold"
            style={{
              color: sideColor,
              background: sideColor ? `color-mix(in srgb, ${sideColor} 15%, transparent)` : undefined,
            }}
          >
            {data.suggested_side} bias
          </span>
        )}
      </div>

      <div className="mt-2 flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span
          className="text-lg font-semibold"
          style={{ color: data.regime ? REGIME_COLOR[data.regime] : undefined }}
        >
          {data.regime ?? "—"}
        </span>
        <span className="text-xs text-[var(--ink-muted)]">
          {data.trend_strength} trend · {data.volatility_state} vol
        </span>
      </div>

      {data.summary && (
        <p className="mt-3 text-sm text-[var(--ink-secondary)]">{data.summary}</p>
      )}

      <div className="mt-3 flex gap-4 text-xs text-[var(--ink-muted)]">
        <span>
          LTP <span className="tabular-nums text-[var(--ink-primary)]">{fmtNumber(data.ltp)}</span>
        </span>
        <span>
          RSI <span className="tabular-nums text-[var(--ink-primary)]">{fmtNumber(data.rsi)}</span>
        </span>
        <span>
          ADX <span className="tabular-nums text-[var(--ink-primary)]">{fmtNumber(data.adx)}</span>
        </span>
      </div>
    </div>
  )
}
