import { useEffect } from "react"
import { useLiveStore } from "../store/liveStore"
import { useTrades } from "../hooks/useTrades"
import { StatTile } from "../components/StatTile"
import { PnlText } from "../components/PnlText"
import { MarketTickerBar } from "../components/MarketTickerBar"
import { fmtCurrency, fmtNumber } from "../lib/format"

export function LiveDashboard() {
  const connect = useLiveStore((s) => s.connect)
  const connected = useLiveStore((s) => s.connected)
  const stageResults = useLiveStore((s) => s.stageResults)
  const broker = useLiveStore((s) => s.brokerStatus)
  const positions = useLiveStore((s) => s.positions)
  const marketTicker = useLiveStore((s) => s.marketTicker)
  // Today only, resolved server-side — persisted (survives a mid-day
  // restart) but resets naturally when the next trading day starts,
  // unlike the Trade Log page which shows full history. available_capital/
  // open_positions above stay on the live WebSocket feed since those are
  // genuine live state, not trade history.
  const { trades: todaysTrades } = useTrades({ today: true })

  useEffect(() => {
    connect()
  }, [connect])

  const realizedPnl = todaysTrades.reduce((sum, t) => sum + t.pnl, 0)
  const recentTrades = [...todaysTrades].slice(-8).reverse()

  const funnel: Array<{ label: string; symbols: string[]; color: string }> = [
    { label: "Stage 1", symbols: stageResults.ORB.stage1, color: "var(--status-warning)" },
    { label: "Stage 2", symbols: stageResults.ORB.stage2, color: "var(--status-serious)" },
    { label: "Stage 3", symbols: stageResults.ORB.stage3, color: "var(--status-critical)" },
  ]

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">Live Paper Trading</h1>

      <MarketTickerBar ticker={marketTicker} connected={connected} />

      <div className="grid grid-cols-4 gap-4">
        <StatTile label="Available Capital" value={fmtCurrency(broker.available_capital)} />
        <StatTile label="Open Positions" value={positions.length} />
        <StatTile label="Total Trades" value={todaysTrades.length} />
        <StatTile label="Realized P&L" value={<PnlText value={realizedPnl} />} />
      </div>

      <section className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5">
        <h2 className="mb-4 text-sm font-semibold text-[var(--ink-secondary)]">
          ORB Screener Funnel
        </h2>
        <div className="grid grid-cols-3 gap-4">
          {funnel.map((stage) => (
            <div key={stage.label} className="rounded-md border border-[var(--border)] p-4">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium" style={{ color: stage.color }}>
                  {stage.label}
                </span>
                <span className="tabular-nums text-lg font-semibold">
                  {stage.symbols.length}
                </span>
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {stage.symbols.length === 0 && (
                  <span className="text-xs text-[var(--ink-muted)]">No candidates</span>
                )}
                {stage.symbols.map((sym) => (
                  <span
                    key={sym}
                    className="rounded bg-[var(--surface-2)] px-2 py-0.5 text-xs text-[var(--ink-secondary)]"
                  >
                    {sym}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5">
        <h2 className="mb-4 text-sm font-semibold text-[var(--ink-secondary)]">
          Open Positions
        </h2>
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
                  <td className="py-2">
                    <PnlText value={pos.unrealized_pnl} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5">
        <h2 className="mb-4 text-sm font-semibold text-[var(--ink-secondary)]">
          Recent Trades
        </h2>
        {recentTrades.length === 0 ? (
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
              {recentTrades.map((t, i) => (
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
      </section>
    </div>
  )
}
