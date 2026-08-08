import { useMemo } from "react"
import type { CorrelationPair } from "../../lib/types"
import { EmptyState } from "./EmptyState"

// Diverging around 0: red toward +1 (strategies win/lose on the same
// days — little diversification benefit from running both), green toward
// -1 (offsetting). Same color-mix technique as StrategyHeatmap's
// profit-factor cells.
function cellBackground(correlation: number | null): string {
  if (correlation === null) return "var(--surface-2)"
  const clamped = Math.min(1, Math.max(-1, correlation))
  if (clamped >= 0) {
    return `color-mix(in srgb, var(--status-critical) ${clamped * 70}%, var(--surface-2))`
  }
  return `color-mix(in srgb, var(--status-good) ${-clamped * 70}%, var(--surface-2))`
}

export function StrategyCorrelationMatrix({ pairs }: { pairs: CorrelationPair[] }) {
  const { strategies, lookup } = useMemo(() => {
    const strategySet = new Set<string>()
    const lookup = new Map<string, number | null>()
    for (const p of pairs) {
      strategySet.add(p.strategy_a)
      strategySet.add(p.strategy_b)
      lookup.set(`${p.strategy_a}::${p.strategy_b}`, p.correlation)
      lookup.set(`${p.strategy_b}::${p.strategy_a}`, p.correlation)
    }
    return { strategies: [...strategySet].sort(), lookup }
  }, [pairs])

  if (strategies.length < 2) {
    return (
      <EmptyState
        title="Not enough strategies yet"
        subtitle="Needs at least two strategies with closed trades to compare correlation."
      />
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-max border-separate border-spacing-1 text-xs">
        <thead>
          <tr>
            <th className="px-2 py-1 text-left font-medium text-[var(--ink-muted)]" />
            {strategies.map((s) => (
              <th
                key={s}
                className="whitespace-nowrap px-2 py-1 text-center font-medium text-[var(--ink-muted)]"
              >
                {s}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {strategies.map((rowStrategy) => (
            <tr key={rowStrategy}>
              <td className="whitespace-nowrap px-2 py-1.5 font-medium text-[var(--ink-primary)]">
                {rowStrategy}
              </td>
              {strategies.map((colStrategy) => {
                if (colStrategy === rowStrategy) {
                  return (
                    <td
                      key={colStrategy}
                      className="rounded-lg bg-[var(--surface-2)]/40 px-2 py-1.5 text-center text-[var(--ink-muted)]"
                    >
                      —
                    </td>
                  )
                }

                const correlation = lookup.get(`${rowStrategy}::${colStrategy}`) ?? null
                return (
                  <td
                    key={colStrategy}
                    className="rounded-lg px-2 py-1.5 text-center tabular-nums font-semibold text-[var(--ink-primary)]"
                    style={{ background: cellBackground(correlation) }}
                    title={
                      `${rowStrategy} × ${colStrategy}: ` +
                      (correlation === null ? "not enough overlapping days" : correlation.toFixed(2))
                    }
                  >
                    {correlation === null ? "—" : correlation.toFixed(2)}
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
