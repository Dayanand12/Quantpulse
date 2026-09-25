import type { CandleTimeframe, DeploymentInput, StrategyInfo, Watchlist } from "../lib/types"

const TIMEFRAME_OPTIONS: Array<{ value: CandleTimeframe; label: string }> = [
  { value: "minute", label: "1 minute" },
  { value: "3minute", label: "3 minutes" },
  { value: "5minute", label: "5 minutes" },
  { value: "10minute", label: "10 minutes" },
  { value: "15minute", label: "15 minutes" },
  { value: "30minute", label: "30 minutes" },
]

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

const fieldClass =
  "rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5 text-sm outline-none focus:border-[var(--accent)]"

interface DeploymentFieldsFormProps {
  form: DeploymentInput
  // Narrower than React's full Dispatch<SetStateAction<T>> — this
  // component only ever uses the functional-updater form, so a plain
  // useState setter (create flow) and a null-guarding adapter (edit flow,
  // where the underlying state is DeploymentInput | null) both satisfy it
  // without any type casts at the call site.
  setForm: (updater: (f: DeploymentInput) => DeploymentInput) => void
  strategies: StrategyInfo[]
  watchlist: string[]
  // Named watchlists (id/name/symbols) this deployment can bind to
  // instead of a fixed symbol list — see lib/types.ts's Deployment
  // docstring. A bound deployment re-reads that watchlist's current
  // membership live, no restart needed when it's edited.
  namedWatchlists: Watchlist[]
}

// Every editable field on a deployment — shared by the "New Deployment"
// create form and each card's inline edit mode, so the two never drift.
export function DeploymentFieldsForm({
  form,
  setForm,
  strategies,
  watchlist,
  namedWatchlists,
}: DeploymentFieldsFormProps) {
  function toggleSymbol(symbol: string) {
    setForm((f) => ({
      ...f,
      symbols: f.symbols.includes(symbol)
        ? f.symbols.filter((s) => s !== symbol)
        : [...f.symbols, symbol],
    }))
  }

  const boundWatchlist = namedWatchlists.find((w) => w.id === form.watchlist_id) ?? null

  return (
    <>
      <div className="grid grid-cols-3 gap-4">
        <label className="flex flex-col gap-1">
          <span className="text-xs text-[var(--ink-muted)]">Strategy</span>
          <select
            value={form.strategy_name}
            onChange={(e) => setForm((f) => ({ ...f, strategy_name: e.target.value }))}
            className={fieldClass}
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
              onChange={(e) => setForm((f) => ({ ...f, [field.key]: Number(e.target.value) }))}
              className={fieldClass}
            />
          </label>
        ))}

        <label className="flex flex-col gap-1">
          <span className="text-xs text-[var(--ink-muted)]">Active From</span>
          <input
            type="time"
            value={form.start_time}
            onChange={(e) => setForm((f) => ({ ...f, start_time: e.target.value }))}
            className={fieldClass}
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-xs text-[var(--ink-muted)]">Active Until</span>
          <input
            type="time"
            value={form.end_time}
            onChange={(e) => setForm((f) => ({ ...f, end_time: e.target.value }))}
            className={fieldClass}
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-xs text-[var(--ink-muted)]">Timeframe</span>
          <select
            value={form.timeframe}
            onChange={(e) =>
              setForm((f) => ({ ...f, timeframe: e.target.value as CandleTimeframe }))
            }
            className={fieldClass}
          >
            {TIMEFRAME_OPTIONS.map((tf) => (
              <option key={tf.value} value={tf.value}>
                {tf.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {form.start_time >= form.end_time && (
        <p className="mt-2 text-xs text-[var(--status-critical)]">
          Active From must be earlier than Active Until.
        </p>
      )}

      <div className="mt-4">
        <div className="mb-2 flex items-center gap-3">
          <span className="text-xs text-[var(--ink-muted)]">Symbols</span>
          <div className="flex gap-1 text-xs">
            <button
              type="button"
              onClick={() => setForm((f) => ({ ...f, watchlist_id: null }))}
              className="rounded-full px-3 py-1"
              style={{
                background: form.watchlist_id === null ? "var(--accent)" : "var(--surface-2)",
                color: form.watchlist_id === null ? "white" : "var(--ink-secondary)",
              }}
            >
              Pick manually
            </button>
            <button
              type="button"
              onClick={() =>
                setForm((f) => ({ ...f, watchlist_id: namedWatchlists[0]?.id ?? null, symbols: [] }))
              }
              disabled={namedWatchlists.length === 0}
              className="rounded-full px-3 py-1 disabled:opacity-40"
              style={{
                background: form.watchlist_id !== null ? "var(--accent)" : "var(--surface-2)",
                color: form.watchlist_id !== null ? "white" : "var(--ink-secondary)",
              }}
            >
              Use a watchlist
            </button>
          </div>
        </div>

        {form.watchlist_id !== null ? (
          <div className="flex flex-col gap-2">
            <select
              value={form.watchlist_id}
              onChange={(e) => setForm((f) => ({ ...f, watchlist_id: Number(e.target.value) }))}
              className={fieldClass}
            >
              {namedWatchlists.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name} ({w.symbols.length} symbols)
                </option>
              ))}
            </select>
            <p className="text-xs text-[var(--ink-muted)]">
              Trades whatever {boundWatchlist?.name ?? "this watchlist"} currently contains —
              editing the watchlist later updates this deployment live, no restart needed.
            </p>
            <div className="flex flex-wrap gap-1.5">
              {(boundWatchlist?.symbols ?? []).map((symbol) => (
                <span
                  key={symbol}
                  className="rounded bg-[var(--surface-2)] px-2 py-0.5 text-xs text-[var(--ink-secondary)]"
                >
                  {symbol}
                </span>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
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
        )}
      </div>
    </>
  )
}

export function isDeploymentFormValid(form: DeploymentInput): boolean {
  const hasSymbolSource = form.watchlist_id !== null || form.symbols.length > 0
  return Boolean(form.strategy_name) && hasSymbolSource && form.start_time < form.end_time
}
