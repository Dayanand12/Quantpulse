import type { CandleTimeframe, DeploymentInput, StrategyInfo } from "../lib/types"

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
}

// Every editable field on a deployment — shared by the "New Deployment"
// create form and each card's inline edit mode, so the two never drift.
export function DeploymentFieldsForm({
  form,
  setForm,
  strategies,
  watchlist,
}: DeploymentFieldsFormProps) {
  function toggleSymbol(symbol: string) {
    setForm((f) => ({
      ...f,
      symbols: f.symbols.includes(symbol)
        ? f.symbols.filter((s) => s !== symbol)
        : [...f.symbols, symbol],
    }))
  }

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
    </>
  )
}

export function isDeploymentFormValid(form: DeploymentInput): boolean {
  return Boolean(form.strategy_name) && form.symbols.length > 0 && form.start_time < form.end_time
}
