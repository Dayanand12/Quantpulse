import { useEffect, useState } from "react"
import { backtestApi } from "../../lib/backtestApi"
import type { BacktestRunConfig, StrategyInfo } from "../../lib/backtestTypes"
import type { CandleTimeframe } from "../../lib/types"
import { OptionContractPicker } from "./OptionContractPicker"
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

interface OptionsBacktestFormProps {
  config: BacktestRunConfig
  contractSymbol: string
  onChangeConfig: (config: BacktestRunConfig) => void
  onChangeContract: (symbol: string) => void
  onRun: () => void
  running: boolean
}

// Options counterpart to BacktestForm.tsx — same shared risk/sizing
// fields (strategy, timeframe, quantity, SL/TP/trailing, dates, charges),
// but OptionContractPicker replaces the watchlist/symbol-list picker
// since a single backtest here targets exactly one contract (manual
// underlying/expiry/strike/side selection — see this project's Phase 4
// scope decision, no auto-ATM/rolling logic). Deliberately no Clone/
// Delete strategy controls here — that's strategy-authoring workflow,
// kept on the equity Backtest page where it originated.
export function OptionsBacktestForm({
  config,
  contractSymbol,
  onChangeConfig,
  onChangeContract,
  onRun,
  running,
}: OptionsBacktestFormProps) {
  const [strategies, setStrategies] = useState<StrategyInfo[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    backtestApi
      .strategies()
      .then((list) => {
        setStrategies(list)
        if (!config.strategy && list.length > 0) {
          onChangeConfig({ ...config, strategy: list[0].name })
        }
      })
      .catch(() => setLoadError("Couldn't reach the backtest server. Is `python run_backtest_server.py` running?"))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function set<K extends keyof BacktestRunConfig>(key: K, value: BacktestRunConfig[K]) {
    onChangeConfig({ ...config, [key]: value })
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
      <h2 className="mb-4 text-sm font-semibold text-[var(--ink-primary)]">Pick a Contract</h2>
      <OptionContractPicker value={contractSymbol} onChange={onChangeContract} />

      <div className="mt-5 border-t border-[var(--glass-border)] pt-4">
        <span className={labelClass}>Strategy</span>
        <select
          className={fieldClass}
          style={{ width: "auto" }}
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
      </div>

      <div className="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
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
          <input type="checkbox" checked={config.charges} onChange={(e) => set("charges", e.target.checked)} />
          <span className="text-sm text-[var(--ink-secondary)]">
            Apply charges (options rate card — flat brokerage, higher STT/exchange fees than equity)
          </span>
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
                  onChangeConfig({
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
            <span className="text-xs text-[var(--ink-muted)]">Full available history for this contract</span>
          )}
        </div>
      </div>

      {config.strategy && <StrategyParamsEditor strategyName={config.strategy} />}

      <button
        onClick={onRun}
        disabled={running || !config.strategy || !contractSymbol}
        className="mt-5 rounded-md bg-[var(--accent)] px-5 py-2 text-sm font-medium text-white disabled:opacity-50"
      >
        {running ? "Running…" : "Run Backtest"}
      </button>
      {!contractSymbol && (
        <p className="mt-2 text-xs text-[var(--ink-muted)]">Pick underlying → expiry → side → strike above first.</p>
      )}
    </div>
  )
}
