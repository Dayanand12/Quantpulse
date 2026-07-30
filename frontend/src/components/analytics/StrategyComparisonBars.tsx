import type { StrategyBreakdown } from "../../lib/types"
import { EmptyState } from "./EmptyState"

const METRICS: {
  key: string
  label: string
  get: (s: StrategyBreakdown) => number | null
  digits: number
}[] = [
  { key: "win_rate", label: "Win Rate %", get: (s) => s.metrics.win_rate, digits: 0 },
  { key: "profit_factor", label: "Profit Factor", get: (s) => s.metrics.profit_factor, digits: 2 },
  { key: "sharpe_ratio", label: "Sharpe Ratio", get: (s) => s.metrics.sharpe_ratio, digits: 2 },
]

// Same accent order as the summary cards, reused here so a given
// strategy's color means the same thing everywhere on the page.
const PALETTE = ["#3987e5", "#34d399", "#a78bfa", "#fb923c", "#2dd4bf", "#ef5a5a"]

export function StrategyComparisonBars({ rows }: { rows: StrategyBreakdown[] }) {
  if (rows.length === 0) {
    return (
      <EmptyState
        title="No strategies to compare"
        subtitle="Deploy more than one strategy to compare them here."
      />
    )
  }

  return (
    <div className="flex flex-col gap-5">
      {METRICS.map((metric) => {
        const values = rows.map((r) => metric.get(r))
        const max = Math.max(...values.filter((v): v is number => v !== null).map(Math.abs), 1)

        return (
          <div key={metric.key}>
            <div className="mb-1.5 text-xs font-medium text-[var(--ink-muted)]">{metric.label}</div>
            <div className="flex flex-col gap-1.5">
              {rows.map((r, i) => {
                const v = metric.get(r)
                const widthPct = v === null ? 0 : (Math.abs(v) / max) * 100

                return (
                  <div key={r.deployment_id ?? i} className="flex items-center gap-2">
                    <span
                      className="w-28 shrink-0 truncate text-xs text-[var(--ink-secondary)]"
                      title={r.strategy_name}
                    >
                      {r.strategy_name}
                    </span>
                    <div className="h-2 flex-1 overflow-hidden rounded-full bg-[var(--surface-2)]">
                      <div
                        className="h-full rounded-full transition-all duration-500 ease-out"
                        style={{ width: `${widthPct}%`, background: PALETTE[i % PALETTE.length] }}
                      />
                    </div>
                    <span className="w-14 shrink-0 text-right text-xs tabular-nums text-[var(--ink-muted)]">
                      {v === null ? "—" : v.toFixed(metric.digits)}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}
