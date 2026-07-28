import { useEffect, useState } from "react"
import { api } from "../lib/api"
import { PnlText } from "../components/PnlText"
import { fmtCurrency } from "../lib/format"
import type { Deployment, DeploymentInput, StrategyInfo } from "../lib/types"

const EMPTY_FORM: DeploymentInput = {
  strategy_name: "",
  symbols: [],
  capital: 50000,
  quantity: 50,
  stoploss_pct: 0.8,
  target_pct: 2.0,
  trailing_pct: 0.1,
  max_cycles_per_day: 10,
  enabled: true,
}

const NUMBER_FIELDS: Array<{
  key: keyof Pick<
    DeploymentInput,
    "capital" | "quantity" | "stoploss_pct" | "target_pct" | "trailing_pct" | "max_cycles_per_day"
  >
  label: string
  step: string
}> = [
  { key: "capital", label: "Capital", step: "1000" },
  { key: "quantity", label: "Quantity / Trade", step: "1" },
  { key: "stoploss_pct", label: "Stop Loss %", step: "0.1" },
  { key: "target_pct", label: "Target %", step: "0.1" },
  { key: "trailing_pct", label: "Trailing Stop %", step: "0.05" },
  { key: "max_cycles_per_day", label: "Max Cycles / Symbol / Day", step: "1" },
]

export function Strategies() {
  const [strategies, setStrategies] = useState<StrategyInfo[]>([])
  const [watchlist, setWatchlist] = useState<string[]>([])
  const [deployments, setDeployments] = useState<Deployment[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [form, setForm] = useState<DeploymentInput>(EMPTY_FORM)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  async function refresh() {
    const [strategiesRes, watchlistRes, deploymentsRes] = await Promise.all([
      api.strategies(),
      api.watchlist(),
      api.deployments(),
    ])
    setStrategies(strategiesRes)
    setWatchlist(watchlistRes.symbols)
    setDeployments(deploymentsRes)
    setForm((f) => (f.strategy_name ? f : { ...f, strategy_name: strategiesRes[0]?.name ?? "" }))
  }

  useEffect(() => {
    refresh()
      .catch(() => setLoadError("Failed to load strategies/deployments."))
      .finally(() => setLoading(false))
  }, [])

  function toggleSymbol(symbol: string) {
    setForm((f) => ({
      ...f,
      symbols: f.symbols.includes(symbol)
        ? f.symbols.filter((s) => s !== symbol)
        : [...f.symbols, symbol],
    }))
  }

  async function handleCreate() {
    setCreating(true)
    setCreateError(null)
    try {
      await api.createDeployment(form)
      setForm({ ...EMPTY_FORM, strategy_name: form.strategy_name })
      await refresh()
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : "Failed to create deployment.")
    } finally {
      setCreating(false)
    }
  }

  async function toggleEnabled(deployment: Deployment) {
    await api.updateDeployment(deployment.id, {
      strategy_name: deployment.strategy_name,
      symbols: deployment.symbols,
      capital: deployment.capital,
      quantity: deployment.quantity,
      stoploss_pct: deployment.stoploss_pct,
      target_pct: deployment.target_pct,
      trailing_pct: deployment.trailing_pct,
      max_cycles_per_day: deployment.max_cycles_per_day,
      enabled: !deployment.enabled,
    })
    await refresh()
  }

  async function handleDelete(id: string) {
    await api.deleteDeployment(id)
    await refresh()
  }

  if (loading) {
    return <p className="text-sm text-[var(--ink-muted)]">Loading…</p>
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">Strategies</h1>
      {loadError && <p className="text-sm text-[var(--status-critical)]">{loadError}</p>}

      <section className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5">
        <h2 className="mb-4 text-sm font-semibold text-[var(--ink-secondary)]">Deployments</h2>

        {deployments.length === 0 ? (
          <p className="text-sm text-[var(--ink-muted)]">
            No deployments yet — create one below.
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            {deployments.map((d) => (
              <div key={d.id} className="rounded-md border border-[var(--border)] p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="font-medium">{d.strategy_name}</span>
                    <span
                      className="ml-2 rounded-full px-2 py-0.5 text-xs"
                      style={{
                        color: d.running ? "var(--status-good)" : "var(--ink-muted)",
                        background: d.running ? "rgba(12,163,12,0.12)" : "transparent",
                      }}
                    >
                      {d.running ? "Running" : d.enabled ? "Pending restart" : "Disabled"}
                    </span>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => toggleEnabled(d)}
                      className="rounded-md border border-[var(--border)] px-3 py-1 text-xs hover:bg-[var(--surface-2)]"
                    >
                      {d.enabled ? "Disable" : "Enable"}
                    </button>
                    <button
                      onClick={() => handleDelete(d.id)}
                      className="rounded-md border border-[var(--border)] px-3 py-1 text-xs text-[var(--status-critical)] hover:bg-[var(--surface-2)]"
                    >
                      Delete
                    </button>
                  </div>
                </div>

                <div className="mt-2 flex flex-wrap gap-1.5">
                  {d.symbols.map((s) => (
                    <span
                      key={s}
                      className="rounded bg-[var(--surface-2)] px-2 py-0.5 text-xs text-[var(--ink-secondary)]"
                    >
                      {s}
                    </span>
                  ))}
                </div>

                <div className="mt-3 grid grid-cols-6 gap-3 text-xs text-[var(--ink-muted)]">
                  <div>
                    Capital
                    <div className="tabular-nums text-sm text-[var(--ink-primary)]">
                      {fmtCurrency(d.capital)}
                    </div>
                  </div>
                  <div>
                    Qty
                    <div className="tabular-nums text-sm text-[var(--ink-primary)]">
                      {d.quantity}
                    </div>
                  </div>
                  <div>
                    SL
                    <div className="tabular-nums text-sm text-[var(--ink-primary)]">
                      {d.stoploss_pct}%
                    </div>
                  </div>
                  <div>
                    Target
                    <div className="tabular-nums text-sm text-[var(--ink-primary)]">
                      {d.target_pct}%
                    </div>
                  </div>
                  <div>
                    Trailing
                    <div className="tabular-nums text-sm text-[var(--ink-primary)]">
                      {d.trailing_pct}%
                    </div>
                  </div>
                  <div>
                    Max Cycles
                    <div className="tabular-nums text-sm text-[var(--ink-primary)]">
                      {d.max_cycles_per_day}
                    </div>
                  </div>
                </div>

                {d.status && (
                  <div className="mt-3 flex gap-4 border-t border-[var(--border)] pt-3 text-xs text-[var(--ink-muted)]">
                    <div>
                      Available:{" "}
                      <span className="tabular-nums text-[var(--ink-primary)]">
                        {fmtCurrency(d.status.available_capital)}
                      </span>
                    </div>
                    <div>
                      Realized P&L: <PnlText value={d.status.realized_pnl} />
                    </div>
                    <div>
                      Trades:{" "}
                      <span className="tabular-nums text-[var(--ink-primary)]">
                        {d.status.total_trades}
                      </span>
                    </div>
                    <div>
                      Open positions:{" "}
                      <span className="tabular-nums text-[var(--ink-primary)]">
                        {d.status.open_position_count}
                      </span>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5">
        <h2 className="mb-1 text-sm font-semibold text-[var(--ink-secondary)]">
          New Deployment
        </h2>
        <p className="mb-4 text-xs text-[var(--ink-muted)]">
          Restart the backend for a new or edited deployment to start running.
        </p>

        <div className="grid grid-cols-3 gap-4">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-[var(--ink-muted)]">Strategy</span>
            <select
              value={form.strategy_name}
              onChange={(e) => setForm((f) => ({ ...f, strategy_name: e.target.value }))}
              className="rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5 text-sm outline-none focus:border-[var(--accent)]"
            >
              {strategies.map((s) => (
                <option key={s.name} value={s.name}>
                  {s.display_name} ({s.side})
                </option>
              ))}
            </select>
          </label>

          {NUMBER_FIELDS.map((field) => (
            <label key={field.key} className="flex flex-col gap-1">
              <span className="text-xs text-[var(--ink-muted)]">{field.label}</span>
              <input
                type="number"
                step={field.step}
                value={form[field.key]}
                onChange={(e) =>
                  setForm((f) => ({ ...f, [field.key]: Number(e.target.value) }))
                }
                className="rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5 text-sm outline-none focus:border-[var(--accent)]"
              />
            </label>
          ))}
        </div>

        <div className="mt-4">
          <span className="text-xs text-[var(--ink-muted)]">Symbols (from Watchlist)</span>
          <div className="mt-2 flex flex-wrap gap-2">
            {watchlist.length === 0 && (
              <span className="text-xs text-[var(--ink-muted)]">
                Watchlist is empty — add symbols on the Settings page first.
              </span>
            )}
            {watchlist.map((symbol) => {
              const selected = form.symbols.includes(symbol)
              return (
                <button
                  key={symbol}
                  type="button"
                  onClick={() => toggleSymbol(symbol)}
                  className="rounded-full px-3 py-1 text-xs"
                  style={{
                    background: selected ? "var(--accent)" : "var(--surface-2)",
                    color: selected ? "white" : "var(--ink-secondary)",
                  }}
                >
                  {symbol}
                </button>
              )
            })}
          </div>
        </div>

        <button
          onClick={handleCreate}
          disabled={creating || !form.strategy_name || form.symbols.length === 0}
          className="mt-4 rounded-md bg-[var(--accent)] px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        >
          {creating ? "Deploying…" : "Deploy Strategy"}
        </button>

        {createError && (
          <p className="mt-2 text-xs text-[var(--status-critical)]">{createError}</p>
        )}
      </section>
    </div>
  )
}
