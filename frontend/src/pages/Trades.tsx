import { useEffect } from "react"
import { useLiveStore } from "../store/liveStore"
import { StatTile } from "../components/StatTile"
import { PnlText } from "../components/PnlText"
import { EquityCurve } from "../components/EquityCurve"
import { fmtNumber, fmtPercent } from "../lib/format"

export function Trades() {
  const connect = useLiveStore((s) => s.connect)
  const broker = useLiveStore((s) => s.brokerStatus)

  useEffect(() => {
    connect()
  }, [connect])

  const trades = [...broker.trade_log].reverse()
  const totalPnl = broker.trade_log.reduce((sum, t) => sum + t.pnl, 0)
  const wins = broker.trade_log.filter((t) => t.pnl > 0).length
  const winRate = broker.trade_log.length > 0 ? (wins / broker.trade_log.length) * 100 : null

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">Trade Log</h1>

      <div className="grid grid-cols-3 gap-4">
        <StatTile label="Total Trades" value={broker.trade_log.length} />
        <StatTile label="Win Rate" value={fmtPercent(winRate)} sub={`${wins} winners`} />
        <StatTile label="Total P&L" value={<PnlText value={totalPnl} />} />
      </div>

      <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5">
        <h2 className="mb-4 text-sm font-semibold text-[var(--ink-secondary)]">Equity Curve</h2>
        <EquityCurve trades={broker.trade_log} />
      </div>

      <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5">
        {trades.length === 0 ? (
          <p className="text-sm text-[var(--ink-muted)]">No trades yet.</p>
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
                <th className="pb-2 font-normal">P&L</th>
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
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
