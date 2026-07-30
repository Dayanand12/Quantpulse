import { useEffect, useRef } from "react"
import { HistogramSeries, createChart } from "lightweight-charts"
import type { PeriodPnl } from "../../lib/types"
import { EmptyState } from "./EmptyState"
import { baseChartOptions, toUtcTimestamp } from "./chartTheme"

export function MonthlyPnlChart({ points }: { points: PeriodPnl[] }) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container || points.length === 0) return

    const chart = createChart(container, baseChartOptions(container.clientWidth, 220))
    const series = chart.addSeries(HistogramSeries, { priceLineVisible: false })

    series.setData(
      points.map((p) => ({
        time: toUtcTimestamp(p.bucket),
        value: p.pnl,
        color: p.pnl >= 0 ? "#34d399" : "#ef5a5a",
      })),
    )
    chart.timeScale().fitContent()

    const handleResize = () => chart.applyOptions({ width: container.clientWidth })
    window.addEventListener("resize", handleResize)

    return () => {
      window.removeEventListener("resize", handleResize)
      chart.remove()
    }
  }, [points])

  if (points.length === 0) {
    return (
      <EmptyState title="No P&L data yet" subtitle="Period P&L will appear once trades close." />
    )
  }

  return <div ref={containerRef} className="w-full" />
}
