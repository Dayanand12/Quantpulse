import { useEffect, useState } from "react"
import { backtestApi } from "../../lib/backtestApi"
import type { BacktestRunConfig, StrategyInfo } from "../../lib/backtestTypes"
import type { CandleTimeframe } from "../../lib/types"
import { StrategyParamsEditor } from "./StrategyParamsEditor"

const TIMEFRAMES: CandleTimeframe[] = ["minute", "3minute", "5minute", "10minute", "15minute", "30minute"]

const DATE_PRESETS: { label: string; years: number | null }[] = [
  { label: "1Y", years: 1 },
  { label: "2Y", years: 2 },
  { label: "5Y", years: 5 },
  { label: "All", years: null },
]

function isoDateYearsAgo(years: number): string {
  const d = new Date()
  d.setFullYear(d.getFullYear() - years)
  return d.toISOString().slice(0, 10)
}

const fieldClass =
  "w-full rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5 text-sm outline-none focus:border-[var(--accent)]"
const labelClass = "mb-1 block text-xs font-medium text-[var(--ink-secondary)]"

interface BacktestFormProps {
  config: BacktestRunConfig
  onChange: (config: BacktestRunConfig) => void
  onRun: (config: BacktestRunConfig) => void
  running: boolean
}

export function BacktestForm({ config, onChange, onRun, running }: BacktestFormProps) {
  const [strategies, setStrategies] = useState<StrategyInfo[]>([])
  const [watchlist, setWatchlist] = useState<string[]>([])
  const [useWholeWatchlist, setUseWholeWatchlist] = useState(true)
  const [symbolsText, setSymbolsText] = useState("")
  const [loadError, setLoadError] = useState<string | null>(null)

  const [showClone, setShowClone] = useState(false)
  const [cloneName, setCloneName] = useState("")
  const [cloneStatus, setCloneStatus] = useState<"idle" | "cloning" | "error">("idle")
  const [cloneError, setCloneError] = useState<string | null>(null)

  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [deleteStatus, setDeleteStatus] = useState<"idle" | "deleting" | "error">("idle")
  const [deleteError, setDeleteError] = useState<string | null>(null)

  function loadStrategiesAndWatchlist() {
    return Promise.all([backtestApi.strategies(), backtestApi.watchlist()]).then(([strategyList, wl]) => {
      setStrategies(strategyList)
      setWatchlist(wl.symbols)
      return strategyList
    })
  }

  useEffect(() => {
    loadStrategiesAndWatchlist()
      .then((strategyList) => {
        if (!config.strategy && strategyList.length > 0) {
          onChange({ ...config, strategy: strategyList[0].name })
        }
      })
      .catch(() => setLoadError("Couldn't reach the backtest server. Is `python run_backtest_server.py` running?"))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function handleClone() {
    const name = cloneName.trim()
    if (!name) return

    setCloneStatus("cloning")
    setCloneError(null)
    try {
      const created = await backtestApi.cloneStrategy(config.strategy, name)
      await loadStrategiesAndWatchlist()
      onChange({ ...config, strategy: created.name }) // auto-select the new clone
      setCloneStatus("idle")
      setShowClone(false)
      setCloneName("")
    } catch (e) {
      setCloneError(e instanceof Error ? e.message : "Failed to clone strategy.")
      setCloneStatus("error")
    }
  }

  async function handleDelete() {
    setDeleteStatus("deleting")
    setDeleteError(null)
    try {
      await backtestApi.deleteStrategy(config.strategy)
      const strategyList = await loadStrategiesAndWatchlist()
      onChange({ ...config, strategy: strategyList[0]?.name ?? "" })
      setDeleteStatus("idle")
      setShowDeleteConfirm(false)
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : "Failed to delete strategy.")
      setDeleteStatus("error")
    }
  }

  function set<K extends keyof BacktestRunConfig>(key: K, value: BacktestRunConfig[K]) {
    onChange({ ...config, [key]: value })
  }

  function handleRun() {
    const symbols = useWholeWatchlist
      ? undefined
      : symbolsText
          .split(",")
          .map((s) => s.trim().toUpperCase())
          .filter(Boolean)
    const resolved = { ...config, symbols }
    // Pass the resolved config directly to onRun instead of relying on
    // onChange's setState + a following onRun() reading it back — state
    // updates are async/batched, so a same-tick onChange-then-onRun would
    // fire the request with the PREVIOUS config (this was a real bug:
    // "Specific symbols" silently ran the whole watchlist instead,
    // because the just-typed symbols hadn't landed in state yet).
    onChange(resolved)
    onRun(resolved)
  }

  if (loadError) {
    return (
      <div className="rounded-2xl border border-[var(--status-critical)]/40 bg-[var(--glass-surface)] p-5 text-sm text-[var(--status-critical)]">
        {loadError}
      </div>
    )
  }

  return (
    <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] p-5 backdrop-blur-sm">
      <h2 className="mb-4 text-sm font-semibold text-[var(--ink-primary)]">Configure Backtest</h2>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
        <label>
          <span className={labelClass}>Strategy</span>
          <div className="flex gap-1.5">
            <select
              className={fieldClass}
              value={config.strategy}
              onChange={(e) => set("strategy", e.target.value)}
            >
              {strategies.length === 0 && <option value="">Loading…</option>}
              {strategies.map((s) => (
                <option key={s.name} value={s.name}>
                  {s.display_name}
                </option>
              ))}
            </select>
            <button
              type="button"
              title="Clone this strategy under a new name to tune independently"
              onClick={() => setShowClone((v) => !v)}
              disabled={!config.strategy}
              className="shrink-0 rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-2.5 text-sm hover:bg-[var(--page)] disabled:opacity-50"
            >
              Clone
            </button>
            <button
              type="button"
              title="Delete this strategy — blocked if it's currently used by a deployment"
              onClick={() => setShowDeleteConfirm((v) => !v)}
              disabled={!config.strategy}
              className="shrink-0 rounded-md border border-[var(--status-critical)]/40 bg-[var(--surface-2)] px-2.5 text-sm text-[var(--status-critical)] hover:bg-[var(--status-critical)]/10 disabled:opacity-50"
            >
              Delete
            </button>
          </div>
        </label>

        <label>
          <span className={labelClass}>Timeframe</span>
          <select
            className={fieldClass}
            value={config.timeframe}
            onChange={(e) => set("timeframe", e.target.value as CandleTimeframe)}
          >
            {TIMEFRAMES.map((tf) => (
              <option key={tf} value={tf}>
                {tf}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span className={labelClass}>Quantity</span>
          <input
            type="number"
            className={fieldClass}
            value={config.quantity}
            onChange={(e) => set("quantity", Number(e.target.value))}
          />
        </label>

        <label>
          <span className={labelClass}>Capital (₹)</span>
          <input
            type="number"
            className={fieldClass}
            value={config.capital}
            onChange={(e) => set("capital", Number(e.target.value))}
          />
        </label>

        <label>
          <span className={labelClass}>Stop Loss %</span>
          <input
            type="number"
            step="0.1"
            className={fieldClass}
            value={config.stoploss_pct}
            onChange={(e) => set("stoploss_pct", Number(e.target.value))}
          />
        </label>

        <label>
          <span className={labelClass}>Target %</span>
          <input
            type="number"
            step="0.1"
            className={fieldClass}
            value={config.target_pct}
            onChange={(e) => set("target_pct", Number(e.target.value))}
          />
        </label>

        <label>
          <span className={labelClass}>Trailing %</span>
          <input
            type="number"
            step="0.1"
            className={fieldClass}
            value={config.trailing_pct}
            onChange={(e) => set("trailing_pct", Number(e.target.value))}
          />
        </label>

        <label>
          <span className={labelClass}>Max Cycles/Day</span>
          <input
            type="number"
            className={fieldClass}
            value={config.max_cycles_per_day}
            onChange={(e) => set("max_cycles_per_day", Number(e.target.value))}
          />
        </label>

        <label>
          <span className={labelClass}>Start Time</span>
          <input
            type="time"
            className={fieldClass}
            value={config.start_time}
            onChange={(e) => set("start_time", e.target.value)}
          />
        </label>

        <label>
          <span className={labelClass}>End Time</span>
          <input
            type="time"
            className={fieldClass}
            value={config.end_time}
            onChange={(e) => set("end_time", e.target.value)}
          />
        </label>

        <label className="flex items-end gap-2 pb-2">
          <input
            type="checkbox"
            checked={config.charges}
            onChange={(e) => set("charges", e.target.checked)}
          />
          <span className="text-sm text-[var(--ink-secondary)]">Apply charges (net P&L)</span>
        </label>
      </div>

      <div className="mt-5 border-t border-[var(--glass-border)] pt-4">
        <span className={labelClass}>Date Range</span>
        <div className="flex flex-wrap items-center gap-3">
          <input
            type="date"
            className={fieldClass}
            style={{ width: "auto" }}
            value={config.date_from}
            onChange={(e) => set("date_from", e.target.value)}
          />
          <span className="text-sm text-[var(--ink-muted)]">to</span>
          <input
            type="date"
            className={fieldClass}
            style={{ width: "auto" }}
            value={config.date_to}
            onChange={(e) => set("date_to", e.target.value)}
          />
          <div className="flex gap-1.5">
            {DATE_PRESETS.map((preset) => (
              <button
                key={preset.label}
                type="button"
                onClick={() =>
                  onChange({
                    ...config,
                    date_from: preset.years === null ? "" : isoDateYearsAgo(preset.years),
                    date_to: preset.years === null ? "" : new Date().toISOString().slice(0, 10),
                  })
                }
                className="rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1 text-xs hover:bg-[var(--page)]"
              >
                {preset.label}
              </button>
            ))}
          </div>
          {!config.date_from && !config.date_to && (
            <span className="text-xs text-[var(--ink-muted)]">Full available history</span>
          )}
        </div>
      </div>

      {showClone && (
        <div className="mt-4 rounded-lg border border-[var(--glass-border)] bg-[var(--surface-2)] p-3">
          <p className="mb-2 text-xs text-[var(--ink-muted)]">
            Creates <code>strategies/{cloneName.trim() || "…"}.py</code> as an independent copy of{" "}
            <strong>{config.strategy}</strong> — tune it, backtest it, and if it works, deploy it
            live from the Strategies page. The original is never modified.
          </p>
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="e.g. vwap_reclaim_backtest"
              value={cloneName}
              onChange={(e) => {
                setCloneName(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_"))
                setCloneStatus("idle")
              }}
              className={fieldClass}
            />
            <button
              onClick={handleClone}
              disabled={cloneStatus === "cloning" || !cloneName.trim()}
              className="shrink-0 rounded-md bg-[var(--accent)] px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              {cloneStatus === "cloning" ? "Cloning…" : "Create Clone"}
            </button>
          </div>
          {cloneError && <p className="mt-2 text-xs text-[var(--status-critical)]">{cloneError}</p>}
        </div>
      )}

      {showDeleteConfirm && (
        <div className="mt-4 rounded-lg border border-[var(--status-critical)]/40 bg-[var(--surface-2)] p-3">
          <p className="mb-2 text-xs text-[var(--ink-secondary)]">
            Permanently delete <strong>{config.strategy}</strong> — its source file, params JSON if it
            has one, and this can't be undone. Refused if any deployment (live or paper) is currently
            using it. Stored backtest results for it are kept, not deleted.
          </p>
          <div className="flex gap-2">
            <button
              onClick={handleDelete}
              disabled={deleteStatus === "deleting"}
              className="shrink-0 rounded-md bg-[var(--status-critical)] px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              {deleteStatus === "deleting" ? "Deleting…" : `Yes, delete ${config.strategy}`}
            </button>
            <button
              type="button"
              onClick={() => {
                setShowDeleteConfirm(false)
                setDeleteError(null)
              }}
              className="shrink-0 rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-4 py-1.5 text-sm hover:bg-[var(--page)]"
            >
              Cancel
            </button>
          </div>
          {deleteError && <p className="mt-2 text-xs text-[var(--status-critical)]">{deleteError}</p>}
        </div>
      )}

      {config.strategy && <StrategyParamsEditor strategyName={config.strategy} />}

      <div className="mt-5 border-t border-[var(--glass-border)] pt-4">
        <span className={labelClass}>Symbols</span>
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-1.5 text-sm">
            <input
              type="radio"
              checked={useWholeWatchlist}
              onChange={() => setUseWholeWatchlist(true)}
            />
            Whole watchlist ({watchlist.length} symbols)
          </label>
          <label className="flex items-center gap-1.5 text-sm">
            <input
              type="radio"
              checked={!useWholeWatchlist}
              onChange={() => setUseWholeWatchlist(false)}
            />
            Specific symbols
          </label>
        </div>
        {!useWholeWatchlist && (
          <input
            type="text"
            list="watchlist-symbols"
            placeholder="e.g. RELIANCE, TCS, INFY"
            value={symbolsText}
            onChange={(e) => setSymbolsText(e.target.value)}
            className={`${fieldClass} mt-2`}
          />
        )}
        <datalist id="watchlist-symbols">
          {watchlist.map((s) => (
            <option key={s} value={s} />
          ))}
        </datalist>
      </div>

      <button
        onClick={handleRun}
        disabled={running || !config.strategy}
        className="mt-5 rounded-md bg-[var(--accent)] px-5 py-2 text-sm font-medium text-white disabled:opacity-50"
      >
        {running ? "Running…" : "Run Backtest"}
      </button>
    </div>
  )
}
