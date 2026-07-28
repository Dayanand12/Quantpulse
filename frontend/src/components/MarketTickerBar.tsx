import type { MarketTicker } from "../lib/types"
import { fmtNumber, fmtPercent } from "../lib/format"

const DISPLAY_NAMES: Record<string, string> = {
  "NIFTY 50": "NIFTY 50",
  "NIFTY BANK": "BANKNIFTY",
}

export function MarketTickerBar({
  ticker,
  connected,
}: {
  ticker: MarketTicker
  connected: boolean
}) {
  const symbols = Object.keys(ticker)

  return (
    <section className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="flex flex-wrap items-center gap-6">
        <div className="flex items-center gap-2">
          <span
            className="h-2 w-2 rounded-full"
            style={{
              backgroundColor: connected ? "var(--status-good)" : "var(--status-critical)",
            }}
          />
          <span className="text-xs font-medium text-[var(--ink-muted)]">
            {connected ? "Live" : "Disconnected"}
          </span>
        </div>

        {symbols.length === 0 && (
          <span className="text-sm text-[var(--ink-muted)]">Waiting for market data…</span>
        )}

        {symbols.map((symbol) => {
          const entry = ticker[symbol]
          const change = entry.change
          const color =
            change === null
              ? "var(--ink-secondary)"
              : change >= 0
                ? "var(--status-good)"
                : "var(--status-critical)"
          const sign = change !== null && change > 0 ? "+" : ""

          return (
            <div key={symbol} className="flex items-baseline gap-2">
              <span className="text-sm font-semibold">{DISPLAY_NAMES[symbol] ?? symbol}</span>
              <span className="tabular-nums text-lg font-semibold">{fmtNumber(entry.ltp)}</span>
              {change !== null && (
                <span className="tabular-nums text-sm font-medium" style={{ color }}>
                  {sign}
                  {fmtNumber(change)} ({sign}
                  {fmtPercent(entry.change_pct)})
                </span>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}
