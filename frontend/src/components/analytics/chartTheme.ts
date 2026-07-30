import { ColorType, type UTCTimestamp } from "lightweight-charts"

// lightweight-charts plots on <canvas>, so it needs epoch seconds, not an
// ISO string — this is the one place that conversion happens.
export function toUtcTimestamp(isoDateOrDatetime: string): UTCTimestamp {
  return (Date.parse(isoDateOrDatetime) / 1000) as UTCTimestamp
}

// Shared lightweight-charts options so every chart on the analytics page
// reads as one system instead of four independently themed widgets.
export function baseChartOptions(width: number, height: number) {
  return {
    width,
    height,
    layout: {
      background: { type: ColorType.Solid, color: "transparent" },
      textColor: "#c3c2b7",
    },
    grid: {
      vertLines: { color: "#2c2c2a" },
      horzLines: { color: "#2c2c2a" },
    },
    rightPriceScale: { borderColor: "#2c2c2a" },
    timeScale: { borderColor: "#2c2c2a" },
  }
}
