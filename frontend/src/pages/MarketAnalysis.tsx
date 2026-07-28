import { useEffect, useState } from "react"
import { api } from "../lib/api"
import { StatTile } from "../components/StatTile"
import { fmtPercent } from "../lib/format"
import type { MarketAnalysis as MarketAnalysisData } from "../lib/types"

const DECISION_COLOR: Record<string, string> = {
  "NO TRADE": "var(--ink-muted)",
  "SELL REDUCED SIZE": "var(--status-warning)",
  "SELL NORMAL SIZE": "var(--status-critical)",
}

export function MarketAnalysis() {
  const [symbol, setSymbol] = useState("NIFTY 50")
  const [data, setData] = useState<MarketAnalysisData | null>(null)
  const [downloading, setDownloading] = useState(false)

  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const result = await api.marketAnalysis(symbol)
        if (!cancelled) setData(result)
      } catch {
        if (!cancelled) setData({ error: "Failed to reach backend." })
      }
    }

    poll()
    const id = setInterval(poll, 5000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [symbol])

  async function handleDownload() {
    setDownloading(true)
    try {
      await api.downloadReport(symbol)
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Market Analysis</h1>
        <div className="flex items-center gap-3">
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5 text-sm outline-none focus:border-[var(--accent)]"
            placeholder="Symbol, e.g. NIFTY 50"
          />
          <button
            onClick={handleDownload}
            disabled={downloading}
            className="rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5 text-sm hover:bg-[var(--surface)] disabled:opacity-50"
          >
            {downloading ? "Generating…" : "Download Report"}
          </button>
        </div>
      </div>

      {data?.error ? (
        <p className="text-sm text-[var(--ink-muted)]">{data.error}</p>
      ) : (
        <>
          <div className="grid grid-cols-4 gap-4">
            <StatTile label="Regime" value={data?.regime ?? "—"} />
            <StatTile label="Trend Strength" value={data?.trend_strength ?? "—"} />
            <StatTile label="Volatility" value={data?.volatility_state ?? "—"} />
            <StatTile label="Confidence Score" value={data?.confidence_score ?? "—"} />
          </div>

          <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-6">
            <div className="text-sm text-[var(--ink-muted)]">Decision</div>
            <div
              className="mt-1 text-3xl font-semibold"
              style={{ color: data?.decision ? DECISION_COLOR[data.decision] : undefined }}
            >
              {data?.decision ?? "—"}
            </div>
            <div className="mt-3 text-sm text-[var(--ink-secondary)]">
              ATR: {fmtPercent(data?.atr_pct)} · as of {data?.time ?? "—"}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
