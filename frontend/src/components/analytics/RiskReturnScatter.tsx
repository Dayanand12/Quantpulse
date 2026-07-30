import { useState } from "react"
import type { StrategyBreakdown } from "../../lib/types"
import { EmptyState } from "./EmptyState"

const PALETTE = ["#3987e5", "#34d399", "#a78bfa", "#fb923c", "#2dd4bf", "#ef5a5a"]

interface ScatterPoint {
  row: StrategyBreakdown
  ddPct: number
  returnPct: number
}

export function RiskReturnScatter({ rows }: { rows: StrategyBreakdown[] }) {
  const [hovered, setHovered] = useState<string | null>(null)

  const points: ScatterPoint[] = rows.flatMap((row) => {
    const ddPct = row.metrics.max_drawdown_pct
    const returnPct = row.capital > 0 ? (row.metrics.total_pnl / row.capital) * 100 : null
    return ddPct === null || returnPct === null ? [] : [{ row, ddPct, returnPct }]
  })

  if (points.length === 0) {
    return (
      <EmptyState
        title="Not enough data yet"
        subtitle="Needs at least one strategy with capital and a closed trade."
      />
    )
  }

  const width = 100
  const height = 100
  const maxDd = Math.max(...points.map((p) => p.ddPct), 1)
  const maxAbsReturn = Math.max(...points.map((p) => Math.abs(p.returnPct)), 1)

  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-[200px] w-full overflow-visible">
        <line x1="0" y1={height / 2} x2={width} y2={height / 2} stroke="#2c2c2a" strokeWidth="0.4" />
        <line x1="4" y1="0" x2="4" y2={height} stroke="#2c2c2a" strokeWidth="0.4" />

        {points.map((p, i) => {
          const cx = 4 + (p.ddPct / maxDd) * (width - 12)
          const cy = height - ((p.returnPct + maxAbsReturn) / (2 * maxAbsReturn)) * height
          const sharpe = p.row.metrics.sharpe_ratio
          const radius = sharpe === null ? 3 : Math.min(7, Math.max(2.5, Math.abs(sharpe) * 1.5))
          const color = PALETTE[i % PALETTE.length]
          const dimmed = hovered !== null && hovered !== p.row.strategy_name

          return (
            <circle
              key={p.row.deployment_id ?? i}
              cx={cx}
              cy={cy}
              r={radius}
              fill={color}
              opacity={dimmed ? 0.25 : 0.85}
              style={{ transition: "opacity 200ms ease" }}
              onMouseEnter={() => setHovered(p.row.strategy_name)}
              onMouseLeave={() => setHovered(null)}
            >
              <title>
                {p.row.strategy_name}: {p.returnPct.toFixed(1)}% return, {p.ddPct.toFixed(1)}%
                drawdown{sharpe !== null ? `, Sharpe ${sharpe.toFixed(2)}` : ""}
              </title>
            </circle>
          )
        })}
      </svg>

      <div className="mt-1 flex items-center justify-between text-[10px] text-[var(--ink-muted)]">
        <span>↑ Return %</span>
        <span>Drawdown % →</span>
      </div>

      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
        {points.map((p, i) => (
          <button
            key={p.row.deployment_id ?? i}
            type="button"
            onMouseEnter={() => setHovered(p.row.strategy_name)}
            onMouseLeave={() => setHovered(null)}
            className="flex items-center gap-1.5 text-xs text-[var(--ink-muted)] transition-colors hover:text-[var(--ink-primary)]"
          >
            <span className="h-2 w-2 rounded-full" style={{ background: PALETTE[i % PALETTE.length] }} />
            {p.row.strategy_name}
          </button>
        ))}
      </div>
    </div>
  )
}
