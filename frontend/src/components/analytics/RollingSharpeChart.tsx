import { useEffect, useMemo, useRef } from "react"
import { LineSeries, createChart } from "lightweight-charts"
import type { RollingSharpePoint } from "../../lib/types"
import { EmptyState } from "./EmptyState"
import { baseChartOptions, toUtcTimestamp } from "./chartTheme"

export function RollingSharpeChart({ points }: { points: RollingSharpePoint[] }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const usable = useMemo(() => points.filter((p) => p.sharpe_ratio !== null), [points])

  useEffect(() => {
    const container = containerRef.current
    if (!container || usable.length === 0) return

    const chart = createChart(container, baseChartOptions(container.clientWidth, 220))
    const series = chart.addSeries(LineSeries, {
      color: "#a78bfa",
      lineWidth: 2,
      priceLineVisible: false,
    })

    series.setData(
      usable.map((p) => ({ time: toUtcTimestamp(p.date), value: p.sharpe_ratio as number })),
    )
    chart.timeScale().fitContent()

    const handleResize = () => chart.applyOptions({ width: container.clientWidth })
    window.addEventListener("resize", handleResize)

    return () => {
      window.removeEventListener("resize", handleResize)
      chart.remove()
    }
  }, [usable])

  if (usable.length === 0) {
    return (
      <EmptyState
        title="Not enough data yet"
        subtitle="Rolling Sharpe needs a longer trading history."
      />
    )
  }

  return <div ref={containerRef} className="w-full" />
}
