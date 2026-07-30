import { useState } from "react"
import { api } from "../lib/api"
import { IndexReadCard } from "../components/IndexReadCard"
import { StatTile } from "../components/StatTile"
import { useMarketAnalysis } from "../hooks/useMarketAnalysis"
import { fmtNumber, fmtPercent } from "../lib/format"

const DECISION_COLOR: Record<string, string> = {
  "NO TRADE": "var(--ink-muted)",
  "SELL REDUCED SIZE": "var(--status-warning)",
  "SELL NORMAL SIZE": "var(--status-critical)",
  "BUY REDUCED SIZE": "var(--status-warning)",
  "BUY NORMAL SIZE": "var(--status-good)",
}

const WATCHED_INDICES = ["NIFTY 50", "NIFTY BANK"]

export function MarketAnalysis() {
  const [symbol, setSymbol] = useState("NIFTY 50")
  const [downloading, setDownloading] = useState(false)
  const data = useMarketAnalysis(symbol)

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
      <div>
        <h1 className="text-2xl font-semibold">Market Analysis</h1>
        <p className="mt-1 text-sm text-[var(--ink-muted)]">
          Today's Read updates automatically. Search any other symbol below for the same
          breakdown, including the raw numbers to cross-check against your broker's chart.
        </p>
      </div>

      <div>
        <h2 className="mb-2 text-sm font-semibold text-[var(--ink-secondary)]">Today's Read</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {WATCHED_INDICES.map((s) => (
            <IndexReadCardWithPolling key={s} symbol={s} />
          ))}
        </div>
      </div>

      <div className="flex items-center justify-between border-t border-[var(--border)] pt-6">
        <h2 className="text-sm font-semibold text-[var(--ink-secondary)]">Symbol Lookup</h2>
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
          <div>
            <div className="mb-2 flex items-baseline justify-between">
              <h3 className="text-sm font-semibold text-[var(--ink-secondary)]">
                Raw Indicators
              </h3>
              {data?.as_of && (
                <span className="text-xs text-[var(--ink-muted)]">
                  As of last closed 1-min candle: {data.as_of} — compare Zerodha's chart at this
                  exact candle, not "now" (its live chart includes the still-forming candle).
                </span>
              )}
            </div>
            <div className="grid grid-cols-4 gap-4 lg:grid-cols-8">
              <StatTile label="LTP" value={fmtNumber(data?.ltp)} />
              <StatTile label="EMA 5" value={fmtNumber(data?.ema5)} />
              <StatTile label="EMA 9" value={fmtNumber(data?.ema9)} />
              <StatTile label="EMA 21" value={fmtNumber(data?.ema21)} />
              <StatTile label="RSI 14" value={fmtNumber(data?.rsi)} />
              <StatTile label="ADX 14" value={fmtNumber(data?.adx)} />
              <StatTile label="VWAP" value={fmtNumber(data?.vwap)} />
              <StatTile label="Volume Ratio" value={fmtNumber(data?.volume_ratio)} />
            </div>
          </div>

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
            {data?.summary && (
              <p className="mt-2 text-sm text-[var(--ink-secondary)]">{data.summary}</p>
            )}
            <div className="mt-3 text-sm text-[var(--ink-secondary)]">
              ATR: {fmtPercent(data?.atr_pct)} · as of {data?.time ?? "—"}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

function IndexReadCardWithPolling({ symbol }: { symbol: string }) {
  const data = useMarketAnalysis(symbol)
  return <IndexReadCard symbol={symbol} data={data} />
}
