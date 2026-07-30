import { useEffect, useRef } from "react"
import { AreaSeries, createChart } from "lightweight-charts"
import type { DrawdownPoint } from "../../lib/types"
import { EmptyState } from "./EmptyState"
import { baseChartOptions, toUtcTimestamp } from "./chartTheme"

export function DrawdownChart({ points }: { points: DrawdownPoint[] }) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container || points.length === 0) return

    const chart = createChart(container, baseChartOptions(container.clientWidth, 220))
    const series = chart.addSeries(AreaSeries, {
      lineColor: "#ef5a5a",
      topColor: "rgba(239, 90, 90, 0.02)",
      bottomColor: "rgba(239, 90, 90, 0.35)",
      lineWidth: 2,
      priceLineVisible: false,
    })

    // Drawdown is naturally >= 0 ("how far below the peak") — negate so it
    // reads the conventional way: dipping below a zero line, not above it.
    series.setData(points.map((p) => ({ time: toUtcTimestamp(p.closed_at), value: -p.drawdown })))
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
        title="No drawdown data yet"
        subtitle="The running drawdown will chart here once trades close."
      />
    )
  }

  return <div ref={containerRef} className="w-full" />
}
