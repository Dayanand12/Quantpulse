import { useMemo, useState } from "react"
import { fmtCurrency, fmtNumber, fmtPercent } from "../../lib/format"
import { formatStrategyParams } from "../../lib/backtestTypes"
import type { BacktestResultSummary } from "../../lib/backtestTypes"
import { EmptyState } from "./EmptyState"

type MetricKey = "total_pnl" | "win_rate" | "profit_factor" | "sharpe_ratio" | "max_drawdown_pct"

const METRICS: { key: MetricKey; label: string; format: (n: number) => string }[] = [
  { key: "total_pnl", label: "Net P&L", format: fmtCurrency },
  { key: "win_rate", label: "Win Rate", format: (n) => fmtPercent(n) },
  { key: "profit_factor", label: "Profit Factor", format: (n) => fmtNumber(n) },
  { key: "sharpe_ratio", label: "Sharpe", format: (n) => fmtNumber(n) },
  { key: "max_drawdown_pct", label: "Max Drawdown %", format: (n) => fmtPercent(n) },
]

function paramLabel(r: BacktestResultSummary): string {
  const paramsPart = formatStrategyParams(r.strategy_params_json)
  return (
    `${r.timeframe} · SL ${r.stoploss_pct} / TP ${r.target_pct} / Trail ${r.trailing_pct}` +
    (paramsPart ? ` · ${paramsPart}` : "")
  )
}

interface BacktestComparisonChartProps {
  results: BacktestResultSummary[]
  selectedId: number | null
  onSelect: (id: number) => void
}

// Every tested parameter combination for a strategy, as horizontal bars
// ranked by whichever metric the user picks — a config sitting near the
// top of the bar list is a config visually worth digging into via the
// dropdown above. Deliberately hand-rolled rather than lightweight-charts
// (that library is time-series-axis only; this axis is "which run", not
// "when").
export function BacktestComparisonChart({ results, selectedId, onSelect }: BacktestComparisonChartProps) {
  const [metricKey, setMetricKey] = useState<MetricKey>("total_pnl")
  const metric = METRICS.find((m) => m.key === metricKey)!

  const ranked = useMemo(() => {
    const withValue = results.filter((r) => r[metricKey] !== null)
    const withoutValue = results.filter((r) => r[metricKey] === null)
    withValue.sort((a, b) => (b[metricKey] as number) - (a[metricKey] as number))
    return [...withValue, ...withoutValue]
  }, [results, metricKey])

  const maxAbs = useMemo(
    () => Math.max(1e-9, ...ranked.map((r) => Math.abs((r[metricKey] as number) ?? 0))),
    [ranked, metricKey],
  )

  if (results.length === 0) {
    return (
      <EmptyState
        title="No tested combinations yet"
        subtitle="Run this strategy from the Backtest tab a few times with different settings — every run is logged here automatically."
      />
    )
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <span className="text-xs text-[var(--ink-muted)]">Rank by</span>
        {METRICS.map((m) => (
          <button
            key={m.key}
            onClick={() => setMetricKey(m.key)}
            className={`rounded-md border px-2.5 py-1 text-xs transition-colors ${
              m.key === metricKey
                ? "border-[var(--accent)] bg-[var(--accent)]/15 text-[var(--accent)]"
                : "border-[var(--border)] bg-[var(--surface-2)] text-[var(--ink-secondary)] hover:bg-[var(--page)]"
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>

      <div className="flex max-h-[420px] flex-col gap-1.5 overflow-y-auto pr-1">
        {ranked.map((r) => {
          const value = r[metricKey] as number | null
          const pct = value === null ? 0 : (Math.abs(value) / maxAbs) * 100
          const positive = value !== null && value >= 0
          const isSelected = r.id === selectedId

          return (
            <button
              key={r.id}
              onClick={() => onSelect(r.id)}
              title={`${r.symbols} · ${r.date_from} → ${r.date_to} · ${r.total_trades} trades`}
              className={`group relative overflow-hidden rounded-lg border px-3 py-2 text-left transition-colors ${
                isSelected
                  ? "border-[var(--accent)] bg-[var(--accent)]/10"
                  : "border-[var(--glass-border)] bg-[var(--surface-2)]/60 hover:border-white/20"
              }`}
            >
              <div
                aria-hidden
                className="absolute inset-y-0 left-0 opacity-20"
                style={{
                  width: `${pct}%`,
                  background: positive ? "var(--status-good)" : "var(--status-critical)",
                }}
              />
              <div className="relative flex items-center justify-between gap-3 text-sm">
                <span className="truncate text-[var(--ink-primary)]">{paramLabel(r)}</span>
                <span
                  className="shrink-0 tabular-nums font-semibold"
                  style={{ color: value === null ? "var(--ink-muted)" : positive ? "var(--status-good)" : "var(--status-critical)" }}
                >
                  {value === null ? "—" : metric.format(value)}
                </span>
              </div>
              <div className="relative mt-0.5 text-[11px] text-[var(--ink-muted)]">
                {r.date_from} → {r.date_to} · {r.total_trades} trades
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
