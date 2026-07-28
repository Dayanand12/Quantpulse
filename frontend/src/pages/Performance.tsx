import { useEffect, useState } from "react"
import type { ReactNode } from "react"
import { api } from "../lib/api"
import { PnlText } from "../components/PnlText"
import { fmtCurrency, fmtNumber, fmtPercent } from "../lib/format"
import type { Deployment } from "../lib/types"

function MetricTile({ label, value, na }: { label: string; value: ReactNode; na?: string }) {
  const isMissing = value === null || value === undefined

  return (
    <div className="rounded-md border border-[var(--border)] p-3">
      <div className="text-xs text-[var(--ink-muted)]">{label}</div>
      <div className="tabular-nums mt-1 text-lg font-semibold">
        {isMissing ? (
          <span className="text-sm font-normal text-[var(--ink-muted)]">
            N/A{na ? ` — ${na}` : ""}
          </span>
        ) : (
          value
        )}
      </div>
    </div>
  )
}

export function Performance() {
  const [deployments, setDeployments] = useState<Deployment[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .deployments()
      .then(setDeployments)
      .catch(() => setError("Failed to load deployments."))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return <p className="text-sm text-[var(--ink-muted)]">Loading…</p>
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">Performance</h1>
      {error && <p className="text-sm text-[var(--status-critical)]">{error}</p>}

      {deployments.length === 0 ? (
        <p className="text-sm text-[var(--ink-muted)]">No deployments yet.</p>
      ) : (
        deployments.map((d) => (
          <section
            key={d.id}
            className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5"
          >
            <div className="mb-4 flex items-center justify-between">
              <div>
                <span className="font-medium">{d.strategy_name}</span>
                <span className="ml-2 text-xs text-[var(--ink-muted)]">
                  {d.symbols.join(", ")}
                </span>
              </div>
              {!d.running && (
                <span className="text-xs text-[var(--ink-muted)]">Not currently running</span>
              )}
            </div>

            {!d.status ? (
              <p className="text-sm text-[var(--ink-muted)]">
                No live data yet — restart the backend to activate this deployment.
              </p>
            ) : (
              <div className="grid grid-cols-4 gap-3">
                <MetricTile label="Total Trades" value={d.status.total_trades} />
                <MetricTile
                  label="Win Rate"
                  value={d.status.win_rate !== null ? fmtPercent(d.status.win_rate) : null}
                  na="no trades yet"
                />
                <MetricTile
                  label="Profit Factor"
                  value={
                    d.status.profit_factor !== null ? fmtNumber(d.status.profit_factor) : null
                  }
                  na="no losing trades yet"
                />
                <MetricTile label="Total P&L" value={<PnlText value={d.status.realized_pnl} />} />

                <MetricTile
                  label="Gross Profit"
                  value={<PnlText value={d.status.gross_profit} />}
                />
                <MetricTile label="Gross Loss" value={<PnlText value={d.status.gross_loss} />} />
                <MetricTile
                  label="Max Drawdown"
                  value={`${fmtCurrency(d.status.max_drawdown)}${
                    d.status.max_drawdown_pct !== null
                      ? ` (${fmtPercent(d.status.max_drawdown_pct)})`
                      : ""
                  }`}
                />
                <MetricTile
                  label="Avg R-Multiple"
                  value={
                    d.status.avg_r_multiple !== null
                      ? `${fmtNumber(d.status.avg_r_multiple)}R`
                      : null
                  }
                  na="no trades with a tracked stop-loss yet"
                />

                <MetricTile
                  label="Sharpe Ratio"
                  value={
                    d.status.sharpe_ratio !== null ? fmtNumber(d.status.sharpe_ratio) : null
                  }
                  na="need 2+ trading days"
                />
                <MetricTile
                  label="Available Capital"
                  value={fmtCurrency(d.status.available_capital)}
                />
                <MetricTile label="Open Positions" value={d.status.open_position_count} />
                <MetricTile label="Capital Allocated" value={fmtCurrency(d.capital)} />
              </div>
            )}
          </section>
        ))
      )}
    </div>
  )
}
