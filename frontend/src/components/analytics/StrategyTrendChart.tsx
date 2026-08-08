import { useEffect, useMemo, useRef } from "react"
import { LineSeries, createChart } from "lightweight-charts"
import type { StrategyTrendPoint } from "../../lib/types"
import { EmptyState } from "./EmptyState"
import { baseChartOptions, toUtcTimestamp } from "./chartTheme"

// Same accent order as the other per-strategy charts (StrategyComparisonBars,
// RiskReturnScatter) so a given strategy's color means the same thing
// everywhere on the page.
const PALETTE = ["#3987e5", "#34d399", "#a78bfa", "#fb923c", "#2dd4bf", "#ef5a5a"]

export function StrategyTrendChart({ points }: { points: StrategyTrendPoint[] }) {
  const containerRef = useRef<HTMLDivElement>(null)

  const byStrategy = useMemo(() => {
    const map = new Map<string, StrategyTrendPoint[]>()
    for (const p of points) {
      const list = map.get(p.strategy_name) ?? []
      list.push(p)
      map.set(p.strategy_name, list)
    }
    for (const list of map.values()) list.sort((a, b) => a.bucket.localeCompare(b.bucket))
    return map
  }, [points])

  const strategies = useMemo(() => [...byStrategy.keys()].sort(), [byStrategy])

  useEffect(() => {
    const container = containerRef.current
    if (!container || strategies.length === 0) return

    const chart = createChart(container, baseChartOptions(container.clientWidth, 260))

    strategies.forEach((strategy, i) => {
      const series = chart.addSeries(LineSeries, {
        color: PALETTE[i % PALETTE.length],
        lineWidth: 2,
        priceLineVisible: false,
        title: strategy,
      })
      series.setData(
        (byStrategy.get(strategy) ?? []).map((p) => ({
          time: toUtcTimestamp(p.bucket),
          value: p.cumulative_pnl,
        })),
      )
    })

    chart.timeScale().fitContent()

    const handleResize = () => chart.applyOptions({ width: container.clientWidth })
    window.addEventListener("resize", handleResize)

    return () => {
      window.removeEventListener("resize", handleResize)
      chart.remove()
    }
  }, [byStrategy, strategies])

  if (strategies.length === 0) {
    return (
      <EmptyState
        title="Not enough data yet"
        subtitle="Needs closed trades with a strategy attached to plot per-strategy P&L over time."
      />
    )
  }

  return (
    <div>
      <div ref={containerRef} className="w-full" />
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
        {strategies.map((strategy, i) => (
          <span key={strategy} className="flex items-center gap-1.5 text-xs text-[var(--ink-muted)]">
            <span className="h-2 w-2 rounded-full" style={{ background: PALETTE[i % PALETTE.length] }} />
            {strategy}
          </span>
        ))}
      </div>
    </div>
  )
}
