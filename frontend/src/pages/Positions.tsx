import { useEffect } from "react"
import { useLiveStore } from "../store/liveStore"
import { PnlText } from "../components/PnlText"
import { fmtNumber } from "../lib/format"

export function Positions() {
  const connect = useLiveStore((s) => s.connect)
  const positions = useLiveStore((s) => s.positions)

  useEffect(() => {
    connect()
  }, [connect])

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">Positions</h1>

      <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5">
        {positions.length === 0 ? (
          <p className="text-sm text-[var(--ink-muted)]">No open positions.</p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="text-[var(--ink-muted)]">
              <tr className="border-b border-[var(--border)]">
                <th className="pb-2 font-normal">Strategy</th>
                <th className="pb-2 font-normal">Symbol</th>
                <th className="pb-2 font-normal">Side</th>
                <th className="pb-2 font-normal">Qty</th>
                <th className="pb-2 font-normal">Entry</th>
                <th className="pb-2 font-normal">LTP</th>
                <th className="pb-2 font-normal">Stop Loss</th>
                <th className="pb-2 font-normal">Target</th>
                <th className="pb-2 font-normal">Unrealized P&L</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((pos) => (
                <tr key={pos.symbol} className="border-b border-[var(--border)] last:border-0">
                  <td className="py-2 text-[var(--ink-muted)]">{pos.strategy_name ?? "—"}</td>
                  <td className="py-2 font-medium">{pos.symbol}</td>
                  <td className="py-2">{pos.side}</td>
                  <td className="tabular-nums py-2">{pos.qty}</td>
                  <td className="tabular-nums py-2">{fmtNumber(pos.entry)}</td>
                  <td className="tabular-nums py-2">{fmtNumber(pos.ltp)}</td>
                  <td className="tabular-nums py-2 text-[var(--status-critical)]">
                    {fmtNumber(pos.stop_loss)}
                  </td>
                  <td className="tabular-nums py-2 text-[var(--status-good)]">
                    {fmtNumber(pos.target)}
                  </td>
                  <td className="py-2">
                    <PnlText value={pos.unrealized_pnl} />
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
