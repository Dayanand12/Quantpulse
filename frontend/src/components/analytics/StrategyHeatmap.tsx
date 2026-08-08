import { useMemo } from "react"
import { fmtNumber, fmtPercent } from "../../lib/format"
import type { HeatmapRow } from "../../lib/types"
import { EmptyState } from "./EmptyState"

// Below this many trades, a cell's win rate/profit factor is noise (a
// couple of lucky/unlucky trades reading as "hot"/"cold") — same guard as
// the regime accuracy stat on the Market Analysis page. Show the sample
// size instead of a color-coded ratio until there's enough of it.
const MIN_SAMPLE = 10

// Diverging around profit_factor = 1.0 (breakeven): green above, red
// below, using the app's existing status colors via color-mix — same
// technique IndexReadCard.tsx already uses for its side badge. Clamped at
// 0.5/2.0 so one outlier ratio doesn't wash out the rest of the scale, and
// capped at 70% mix so the win-rate/n text stays legible over it.
function cellBackground(profitFactor: number | null, totalTrades: number): string {
  if (totalTrades < MIN_SAMPLE) return "var(--surface-2)"
  if (profitFactor === null) return "color-mix(in srgb, var(--status-good) 70%, var(--surface-2))"

  const clamped = Math.min(2, Math.max(0.5, profitFactor))
  if (clamped >= 1) {
    const pct = ((clamped - 1) / (2 - 1)) * 70
    return `color-mix(in srgb, var(--status-good) ${pct}%, var(--surface-2))`
  }
  const pct = ((1 - clamped) / (1 - 0.5)) * 70
  return `color-mix(in srgb, var(--status-critical) ${pct}%, var(--surface-2))`
}

interface StrategyHeatmapProps {
  rows: HeatmapRow[]
  columnLabel: string // e.g. "Symbol" or "Market Condition" — column header tooltip only
  emptySubtitle: string
}

export function StrategyHeatmap({ rows, columnLabel, emptySubtitle }: StrategyHeatmapProps) {
  const { strategies, columns, lookup } = useMemo(() => {
    const lookup = new Map<string, HeatmapRow>()
    const colTotals = new Map<string, number>()
    const strategySet = new Set<string>()

    for (const r of rows) {
      lookup.set(`${r.row}::${r.column}`, r)
      strategySet.add(r.row)
      colTotals.set(r.column, (colTotals.get(r.column) ?? 0) + r.cell.total_trades)
    }

    // Busiest columns first so the long tail of low-volume symbols/
    // conditions doesn't push the ones with real signal off-screen.
    const columns = [...colTotals.keys()].sort((a, b) => colTotals.get(b)! - colTotals.get(a)!)
    const strategies = [...strategySet].sort()

    return { strategies, columns, lookup }
  }, [rows])

  if (rows.length === 0) {
    return <EmptyState title="Not enough data yet" subtitle={emptySubtitle} />
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-max border-separate border-spacing-1 text-xs">
        <thead>
          <tr>
            <th className="px-2 py-1 text-left font-medium text-[var(--ink-muted)]">Strategy</th>
            {columns.map((col) => (
              <th
                key={col}
                title={columnLabel}
                className="whitespace-nowrap px-2 py-1 text-center font-medium text-[var(--ink-muted)]"
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {strategies.map((strategy) => (
            <tr key={strategy}>
              <td className="whitespace-nowrap px-2 py-1.5 font-medium text-[var(--ink-primary)]">
                {strategy}
              </td>
              {columns.map((col) => {
                const entry = lookup.get(`${strategy}::${col}`)
                if (!entry) {
                  return (
                    <td
                      key={col}
                      className="rounded-lg bg-[var(--surface-2)]/40 px-2 py-1.5 text-center text-[var(--ink-muted)]"
                    >
                      —
                    </td>
                  )
                }

                const { cell } = entry
                const notEnoughData = cell.total_trades < MIN_SAMPLE

                return (
                  <td
                    key={col}
                    className="rounded-lg px-2 py-1.5 text-center tabular-nums"
                    style={{ background: cellBackground(cell.profit_factor, cell.total_trades) }}
                    title={
                      `${strategy} × ${col}: ${cell.total_trades} trades, ` +
                      `win rate ${cell.win_rate === null ? "—" : fmtPercent(cell.win_rate)}, ` +
                      `profit factor ${cell.profit_factor === null ? "—" : fmtNumber(cell.profit_factor)}, ` +
                      `net P&L ${fmtNumber(cell.total_pnl)}`
                    }
                  >
                    {notEnoughData ? (
                      <>
                        <div className="text-[var(--ink-muted)]">n={cell.total_trades}</div>
                        <div className="text-[10px] text-[var(--ink-muted)]">/{MIN_SAMPLE} min</div>
                      </>
                    ) : (
                      <>
                        <div className="font-semibold text-[var(--ink-primary)]">
                          {cell.win_rate === null ? "—" : fmtPercent(cell.win_rate)}
                        </div>
                        <div className="text-[10px] text-[var(--ink-muted)]">n={cell.total_trades}</div>
                      </>
                    )}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
