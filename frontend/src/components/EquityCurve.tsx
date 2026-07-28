import { useEffect, useRef } from "react"
import { AreaSeries, ColorType, createChart, type UTCTimestamp } from "lightweight-charts"
import type { Trade } from "../lib/types"

const BASE_TIME = 1_700_000_000 // arbitrary anchor; x-axis represents trade sequence, not calendar time
const DAY = 86_400

export function EquityCurve({ trades }: { trades: Trade[] }) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const chart = createChart(container, {
      width: container.clientWidth,
      height: 220,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#c3c2b7",
      },
      grid: {
        vertLines: { color: "#2c2c2a" },
        horzLines: { color: "#2c2c2a" },
      },
      rightPriceScale: { borderColor: "#2c2c2a" },
      timeScale: { visible: false, borderColor: "#2c2c2a" },
      crosshair: { horzLine: { visible: false }, vertLine: { labelVisible: false } },
    })

    const series = chart.addSeries(AreaSeries, {
      lineColor: "#3987e5",
      topColor: "rgba(57, 135, 229, 0.35)",
      bottomColor: "rgba(57, 135, 229, 0.02)",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
    })

    let cumulative = 0
    const data = trades.map((t, i) => {
      cumulative += t.pnl
      return { time: (BASE_TIME + i * DAY) as UTCTimestamp, value: cumulative }
    })

    series.setData(data.length > 0 ? data : [{ time: BASE_TIME as UTCTimestamp, value: 0 }])
    chart.timeScale().fitContent()

    const handleResize = () => chart.applyOptions({ width: container.clientWidth })
    window.addEventListener("resize", handleResize)

    return () => {
      window.removeEventListener("resize", handleResize)
      chart.remove()
    }
  }, [trades])

  return <div ref={containerRef} className="w-full" />
}
