import { useState } from "react"
import { DeploymentFieldsForm, isDeploymentFormValid } from "./DeploymentFieldsForm"
import { PnlText } from "./PnlText"
import { fmtCurrency } from "../lib/format"
import { toDeploymentInput, useStrategiesStore } from "../store/strategiesStore"
import type { Deployment, StrategyInfo, Watchlist } from "../lib/types"

// "5minute" -> "5min", "minute" -> "1min" — compact form for the badge.
const TIMEFRAME_LABEL: Record<string, string> = {
  minute: "1min",
  "3minute": "3min",
  "5minute": "5min",
  "10minute": "10min",
  "15minute": "15min",
  "30minute": "30min",
}

interface DeploymentCardProps {
  deployment: Deployment
  strategies: StrategyInfo[]
  watchlist: string[]
  namedWatchlists: Watchlist[]
}

// One deployment's card — view mode (status/metrics + Edit/Enable-Disable/
// Delete) or, while being edited, the same DeploymentFieldsForm the "New
// Deployment" form uses. Shared between the Deployed Strategies and
// Available Strategies pages so a disabled deployment looks and behaves
// identically wherever it's shown.
export function DeploymentCard({ deployment: d, strategies, watchlist, namedWatchlists }: DeploymentCardProps) {
  const boundWatchlist = namedWatchlists.find((w) => w.id === d.watchlist_id) ?? null
  const toggleEnabled = useStrategiesStore((s) => s.toggleEnabled)
  const deleteDeployment = useStrategiesStore((s) => s.deleteDeployment)
  const updateDeployment = useStrategiesStore((s) => s.updateDeployment)

  const [editing, setEditing] = useState(false)
  const [editForm, setEditForm] = useState(() => toDeploymentInput(d))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function startEdit() {
    setEditForm(toDeploymentInput(d))
    setError(null)
    setEditing(true)
  }

  async function saveEdit() {
    setSaving(true)
    setError(null)
    try {
      await updateDeployment(d.id, editForm)
      setEditing(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save changes.")
    } finally {
      setSaving(false)
    }
  }

  if (editing) {
    return (
      <div className="rounded-md border border-[var(--accent)] p-4">
        <div className="mb-3 flex items-center justify-between">
          <span className="font-medium">Editing {d.strategy_name}</span>
          <div className="flex gap-2">
            <button
              onClick={saveEdit}
              disabled={saving || !isDeploymentFormValid(editForm)}
              className="rounded-md bg-[var(--accent)] px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save Changes"}
            </button>
            <button
              onClick={() => setEditing(false)}
              disabled={saving}
              className="rounded-md border border-[var(--border)] px-3 py-1 text-xs hover:bg-[var(--surface-2)]"
            >
              Cancel
            </button>
          </div>
        </div>

        <DeploymentFieldsForm
          form={editForm}
          setForm={setEditForm}
          strategies={strategies}
          watchlist={watchlist}
          namedWatchlists={namedWatchlists}
        />

        <p className="mt-3 text-xs text-[var(--ink-muted)]">
          Risk/sizing and symbol changes take effect immediately, live — no restart needed.
          Changing the strategy itself stops this deployment until restart (see
          server/main.py::_sync_deployment_runtime).
        </p>
        {error && <p className="mt-2 text-xs text-[var(--status-critical)]">{error}</p>}
      </div>
    )
  }

  return (
    <div className="rounded-md border border-[var(--border)] p-4">
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
            onClick={startEdit}
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
            onClick={() => deleteDeployment(d.id)}
            className="rounded-md border border-[var(--border)] px-3 py-1 text-xs text-[var(--status-critical)] hover:bg-[var(--surface-2)]"
          >
            Delete
          </button>
        </div>
      </div>

      {boundWatchlist && (
        <div className="mt-2 text-xs text-[var(--ink-muted)]">
          Watchlist: <span className="text-[var(--ink-secondary)]">{boundWatchlist.name}</span> — live,
          updates automatically when the watchlist changes
        </div>
      )}
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
              {r.quantity} × {fmtCurrency(r.price)}), only {fmtCurrency(r.available_capital)}{" "}
              available. Reduce quantity or increase capital.
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
          <div className="tabular-nums text-sm text-[var(--ink-primary)]">{d.quantity}</div>
        </div>
        <div>
          SL
          <div className="tabular-nums text-sm text-[var(--ink-primary)]">{d.stoploss_pct}%</div>
        </div>
        <div>
          Target
          <div className="tabular-nums text-sm text-[var(--ink-primary)]">{d.target_pct}%</div>
        </div>
        <div>
          Trailing
          <div className="tabular-nums text-sm text-[var(--ink-primary)]">{d.trailing_pct}%</div>
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
            <span className="tabular-nums text-[var(--ink-primary)]">{d.status.total_trades}</span>
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
  )
}
