import { useEffect, useRef } from "react"
import { AreaSeries, createChart } from "lightweight-charts"
import type { EquityPoint } from "../../lib/types"
import { EmptyState } from "./EmptyState"
import { baseChartOptions, toUtcTimestamp } from "./chartTheme"

export function EquityCurveChart({ points }: { points: EquityPoint[] }) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container || points.length === 0) return

    const chart = createChart(container, baseChartOptions(container.clientWidth, 240))
    const series = chart.addSeries(AreaSeries, {
      lineColor: "#3987e5",
      topColor: "rgba(57, 135, 229, 0.35)",
      bottomColor: "rgba(57, 135, 229, 0.02)",
      lineWidth: 2,
      priceLineVisible: false,
    })

    series.setData(points.map((p) => ({ time: toUtcTimestamp(p.bucket), value: p.cumulative_pnl })))
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
      <EmptyState
        title="No equity data yet"
        subtitle="Closed trades will build the equity curve here."
      />
    )
  }

  return <div ref={containerRef} className="w-full" />
}
