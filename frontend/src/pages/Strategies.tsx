import { useEffect, useState } from "react"
import { api } from "../lib/api"
import { DeploymentFieldsForm, isDeploymentFormValid } from "../components/DeploymentFieldsForm"
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
  start_time: "09:20",
  end_time: "11:30",
  timeframe: "minute",
}

// "5minute" -> "5min", "minute" -> "1min" — compact form for the badge.
const TIMEFRAME_LABEL: Record<string, string> = {
  minute: "1min",
  "3minute": "3min",
  "5minute": "5min",
  "10minute": "10min",
  "15minute": "15min",
  "30minute": "30min",
}

function toDeploymentInput(d: Deployment): DeploymentInput {
  return {
    strategy_name: d.strategy_name,
    symbols: d.symbols,
    capital: d.capital,
    quantity: d.quantity,
    stoploss_pct: d.stoploss_pct,
    target_pct: d.target_pct,
    trailing_pct: d.trailing_pct,
    max_cycles_per_day: d.max_cycles_per_day,
    enabled: d.enabled,
    start_time: d.start_time,
    end_time: d.end_time,
    timeframe: d.timeframe,
  }
}

export function Strategies() {
  const [strategies, setStrategies] = useState<StrategyInfo[]>([])
  const [watchlist, setWatchlist] = useState<string[]>([])
  const [deployments, setDeployments] = useState<Deployment[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [form, setForm] = useState<DeploymentInput>(EMPTY_FORM)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  const [editingId, setEditingId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<DeploymentInput | null>(null)
  const [savingEdit, setSavingEdit] = useState(false)
  const [editError, setEditError] = useState<string | null>(null)

  async function refresh() {
    const [strategiesRes, watchlistsRes, deploymentsRes] = await Promise.all([
      api.strategies(),
      api.watchlists(),
      api.deployments(),
    ])
    setStrategies(strategiesRes)
    // A deployment can be built from any watchlist's symbols — see
    // server/main.py::_validate_deployment_request, which validates
    // against the union of every watchlist, not one specific list.
    setWatchlist([...new Set(watchlistsRes.flatMap((w) => w.symbols))])
    setDeployments(deploymentsRes)
    setForm((f) => (f.strategy_name ? f : { ...f, strategy_name: strategiesRes[0]?.name ?? "" }))
  }

  useEffect(() => {
    refresh()
      .catch(() => setLoadError("Failed to load strategies/deployments."))
      .finally(() => setLoading(false))
  }, [])

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
      ...toDeploymentInput(deployment),
      enabled: !deployment.enabled,
    })
    await refresh()
  }

  async function handleDelete(id: string) {
    await api.deleteDeployment(id)
    await refresh()
  }

  function startEdit(deployment: Deployment) {
    setEditingId(deployment.id)
    setEditForm(toDeploymentInput(deployment))
    setEditError(null)
  }

  function cancelEdit() {
    setEditingId(null)
    setEditForm(null)
    setEditError(null)
  }

  async function saveEdit() {
    if (!editingId || !editForm) return
    setSavingEdit(true)
    setEditError(null)
    try {
      await api.updateDeployment(editingId, editForm)
      cancelEdit()
      await refresh()
    } catch (e) {
      setEditError(e instanceof Error ? e.message : "Failed to save changes.")
    } finally {
      setSavingEdit(false)
    }
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
            {deployments.map((d) =>
              editingId === d.id && editForm ? (
                <div key={d.id} className="rounded-md border border-[var(--accent)] p-4">
                  <div className="mb-3 flex items-center justify-between">
                    <span className="font-medium">Editing {d.strategy_name}</span>
                    <div className="flex gap-2">
                      <button
                        onClick={saveEdit}
                        disabled={savingEdit || !isDeploymentFormValid(editForm)}
                        className="rounded-md bg-[var(--accent)] px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
                      >
                        {savingEdit ? "Saving…" : "Save Changes"}
                      </button>
                      <button
                        onClick={cancelEdit}
                        disabled={savingEdit}
                        className="rounded-md border border-[var(--border)] px-3 py-1 text-xs hover:bg-[var(--surface-2)]"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>

                  <DeploymentFieldsForm
                    form={editForm}
                    setForm={(updater) => setEditForm((prev) => (prev ? updater(prev) : prev))}
                    strategies={strategies}
                    watchlist={watchlist}
                  />

                  <p className="mt-3 text-xs text-[var(--ink-muted)]">
                    Restart the backend for these changes to take effect.
                  </p>
                  {editError && (
                    <p className="mt-2 text-xs text-[var(--status-critical)]">{editError}</p>
                  )}
                </div>
              ) : (
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
                      <span className="ml-2 rounded-full bg-[var(--surface-2)] px-2 py-0.5 text-xs text-[var(--ink-muted)]">
                        Active {d.start_time}–{d.end_time}
                      </span>
                      <span className="ml-2 rounded-full bg-[var(--surface-2)] px-2 py-0.5 text-xs text-[var(--ink-muted)]">
                        {TIMEFRAME_LABEL[d.timeframe] ?? d.timeframe}
                      </span>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => startEdit(d)}
                        className="rounded-md border border-[var(--border)] px-3 py-1 text-xs hover:bg-[var(--surface-2)]"
                      >
                        Edit
                      </button>
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

                  {d.status && d.status.rejected_entries.length > 0 && (
                    <div
                      className="mt-3 flex flex-col gap-1 rounded-md p-3 text-xs"
                      style={{
                        border: "1px solid var(--status-critical)",
                        background: "rgba(230, 103, 103, 0.08)",
                        color: "var(--status-critical)",
                      }}
                    >
                      {d.status.rejected_entries.map((r) => (
                        <div key={r.symbol}>
                          ⚠ {r.symbol} entry skipped — needs {fmtCurrency(r.required_capital)} (
                          {r.quantity} × {fmtCurrency(r.price)}), only{" "}
                          {fmtCurrency(r.available_capital)} available. Reduce quantity or
                          increase capital.
                        </div>
                      ))}
                    </div>
                  )}

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
              ),
            )}
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

        <DeploymentFieldsForm form={form} setForm={setForm} strategies={strategies} watchlist={watchlist} />

        <button
          onClick={handleCreate}
          disabled={creating || !isDeploymentFormValid(form)}
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
