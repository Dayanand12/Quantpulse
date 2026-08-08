import { useTrades } from "../hooks/useTrades"
import { StatTile } from "../components/StatTile"
import { PnlText } from "../components/PnlText"
import { EquityCurve } from "../components/EquityCurve"
import { fmtNumber, fmtPercent } from "../lib/format"

export function Trades() {
  const { trades: allTrades, loading, error } = useTrades()

  const trades = [...allTrades].reverse()
  // net_pnl (post brokerage/STT/exchange/SEBI/stamp duty/GST — see
  // core/domain/charges.py) is what "realized profit" means; fall back to
  // gross pnl only for a trade closed before charges existed.
  const netOf = (t: (typeof allTrades)[number]) => t.net_pnl ?? t.pnl
  const totalPnl = allTrades.reduce((sum, t) => sum + netOf(t), 0)
  const totalCharges = allTrades.reduce((sum, t) => sum + (t.charges ?? 0), 0)
  const wins = allTrades.filter((t) => netOf(t) > 0).length
  const winRate = allTrades.length > 0 ? (wins / allTrades.length) * 100 : null

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">Trade Log</h1>

      {error && <p className="text-sm text-[var(--status-critical)]">{error}</p>}

      <div className="grid grid-cols-4 gap-4">
        <StatTile label="Total Trades" value={allTrades.length} />
        <StatTile label="Win Rate" value={fmtPercent(winRate)} sub={`${wins} winners`} />
        <StatTile label="Realized P&L (net)" value={<PnlText value={totalPnl} />} />
        <StatTile label="Total Charges" value={<PnlText value={-totalCharges} />} />
      </div>

      <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5">
        <h2 className="mb-4 text-sm font-semibold text-[var(--ink-secondary)]">Equity Curve</h2>
        <EquityCurve trades={allTrades} />
      </div>

      <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5">
        {trades.length === 0 ? (
          <p className="text-sm text-[var(--ink-muted)]">
            {loading ? "Loading trades…" : "No trades yet."}
          </p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="text-[var(--ink-muted)]">
              <tr className="border-b border-[var(--border)]">
                <th className="pb-2 font-normal">Strategy</th>
                <th className="pb-2 font-normal">Symbol</th>
                <th className="pb-2 font-normal">Side</th>
                <th className="pb-2 font-normal">Entry</th>
                <th className="pb-2 font-normal">Exit</th>
                <th className="pb-2 font-normal">Qty</th>
                <th className="pb-2 font-normal">Gross P&L</th>
                <th className="pb-2 font-normal">Charges</th>
                <th className="pb-2 font-normal">Net P&L</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t, i) => (
                <tr key={i} className="border-b border-[var(--border)] last:border-0">
                  <td className="py-2 text-[var(--ink-muted)]">{t.strategy_name ?? "—"}</td>
                  <td className="py-2 font-medium">{t.symbol}</td>
                  <td className="py-2">{t.side}</td>
                  <td className="tabular-nums py-2">{fmtNumber(t.entry)}</td>
                  <td className="tabular-nums py-2">{fmtNumber(t.exit)}</td>
                  <td className="tabular-nums py-2">{t.qty}</td>
                  <td className="py-2">
                    <PnlText value={t.pnl} />
                  </td>
                  <td className="tabular-nums py-2 text-[var(--ink-muted)]">
                    {t.charges !== null ? fmtNumber(t.charges) : "—"}
                  </td>
                  <td className="py-2">
                    <PnlText value={netOf(t)} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
