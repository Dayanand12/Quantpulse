import { useState } from "react"
import { PnlText } from "../PnlText"
import { EmptyState } from "../analytics/EmptyState"
import type { BacktestTrade } from "../../lib/backtestTypes"
import { fmtNumber } from "../../lib/format"

const PAGE_SIZE = 50

export function BacktestTradesTable({
  trades,
  truncated,
  showOi = false,
}: {
  trades: BacktestTrade[]
  truncated: boolean
  // Adds an "OI at Entry" column — only meaningful for stock-option
  // trades (see core/domain/models.py::Trade.entry_oi), so equity's
  // Backtest page omits it rather than showing an all-"—" column.
  showOi?: boolean
}) {
  const [page, setPage] = useState(0)
  const pageCount = Math.max(1, Math.ceil(trades.length / PAGE_SIZE))
  const pageTrades = trades.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  if (trades.length === 0) {
    return <EmptyState title="No trades" subtitle="This configuration produced zero trades." />
  }

  return (
    <div>
      {truncated && (
        <p className="mb-3 text-xs text-[var(--ink-muted)]">
          Showing the most recent {trades.length.toLocaleString("en-IN")} trades — the run's summary
          metrics and breakdowns above are computed over every trade, not just what's shown here.
        </p>
      )}

      <div className="max-h-[480px] overflow-auto rounded-xl">
        <table className="w-full border-collapse text-sm">
          <thead className="sticky top-0 z-10 bg-[var(--surface-2)]">
            <tr>
              {[
                "Closed At",
                "Symbol",
                "Side",
                "Entry",
                "Exit",
                "Qty",
                "Gross P&L",
                "Charges",
                "Net P&L",
                "Market Condition",
                ...(showOi ? ["OI at Entry"] : []),
              ].map(
                (h) => (
                  <th
                    key={h}
                    className="whitespace-nowrap px-3 py-2.5 text-left text-xs font-medium text-[var(--ink-muted)]"
                  >
                    {h}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {pageTrades.map((t, i) => (
              <tr
                key={`${t.symbol}-${t.closed_at}-${i}`}
                className={`transition-colors hover:bg-white/[0.04] ${i % 2 === 1 ? "bg-white/[0.015]" : ""}`}
              >
                <td className="whitespace-nowrap border-t border-[var(--glass-border)] px-3 py-2 text-[var(--ink-muted)]">
                  {t.closed_at.replace("T", " ").slice(0, 16)}
                </td>
                <td className="whitespace-nowrap border-t border-[var(--glass-border)] px-3 py-2 font-medium text-[var(--ink-primary)]">
                  {t.symbol}
                </td>
                <td className="whitespace-nowrap border-t border-[var(--glass-border)] px-3 py-2">{t.side}</td>
                <td className="tabular-nums whitespace-nowrap border-t border-[var(--glass-border)] px-3 py-2">
                  {fmtNumber(t.entry)}
                </td>
                <td className="tabular-nums whitespace-nowrap border-t border-[var(--glass-border)] px-3 py-2">
                  {fmtNumber(t.exit)}
                </td>
                <td className="tabular-nums whitespace-nowrap border-t border-[var(--glass-border)] px-3 py-2">{t.qty}</td>
                <td className="whitespace-nowrap border-t border-[var(--glass-border)] px-3 py-2">
                  <PnlText value={t.pnl} />
                </td>
                <td className="tabular-nums whitespace-nowrap border-t border-[var(--glass-border)] px-3 py-2 text-[var(--ink-muted)]">
                  {t.charges !== null ? fmtNumber(t.charges) : "—"}
                </td>
                <td className="whitespace-nowrap border-t border-[var(--glass-border)] px-3 py-2">
                  <PnlText value={t.net_pnl ?? t.pnl} />
                </td>
                <td className="whitespace-nowrap border-t border-[var(--glass-border)] px-3 py-2 text-xs text-[var(--ink-muted)]">
                  {t.market_condition ?? "—"}
                </td>
                {showOi && (
                  <td className="tabular-nums whitespace-nowrap border-t border-[var(--glass-border)] px-3 py-2 text-[var(--ink-muted)]">
                    {t.entry_oi != null ? fmtNumber(t.entry_oi) : "—"}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {pageCount > 1 && (
        <div className="mt-3 flex items-center justify-between text-xs text-[var(--ink-muted)]">
          <span>
            Page {page + 1} of {pageCount} ({trades.length.toLocaleString("en-IN")} trades)
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="rounded-md border border-[var(--glass-border)] px-3 py-1 disabled:opacity-40"
            >
              Prev
            </button>
            <button
              onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
              disabled={page >= pageCount - 1}
              className="rounded-md border border-[var(--glass-border)] px-3 py-1 disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
