import type { Dispatch, SetStateAction } from "react"
import type { AnalyticsFilters, Timeframe } from "../../lib/types"
import { IconRefresh, IconSearch } from "./icons"

interface FilterBarProps {
  filters: AnalyticsFilters
  setFilters: Dispatch<SetStateAction<AnalyticsFilters>>
  onReset: () => void
  availableStrategies: string[]
  availableSymbols: string[]
}

const TIMEFRAMES: { value: Timeframe; label: string }[] = [
  { value: "daily", label: "Daily" },
  { value: "weekly", label: "Weekly" },
  { value: "monthly", label: "Monthly" },
]

const fieldClass =
  "rounded-xl border border-[var(--glass-border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--ink-primary)] outline-none transition-colors focus:border-[var(--accent)]"

export function FilterBar({
  filters,
  setFilters,
  onReset,
  availableStrategies,
  availableSymbols,
}: FilterBarProps) {
  const hasActiveFilters = Boolean(
    filters.strategy || filters.symbol || filters.date_from || filters.date_to,
  )

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] p-4 backdrop-blur-sm">
      <div className="relative">
        <IconSearch className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--ink-muted)]" />
        <select
          aria-label="Filter by symbol"
          className={`${fieldClass} pl-9`}
          value={filters.symbol ?? ""}
          onChange={(e) => setFilters((f) => ({ ...f, symbol: e.target.value || undefined }))}
        >
          <option value="">All symbols</option>
          {availableSymbols.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      <select
        aria-label="Filter by strategy"
        className={fieldClass}
        value={filters.strategy ?? ""}
        onChange={(e) => setFilters((f) => ({ ...f, strategy: e.target.value || undefined }))}
      >
        <option value="">All strategies</option>
        {availableStrategies.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>

      <div className="flex items-center gap-2">
        <input
          aria-label="From date"
          type="date"
          className={fieldClass}
          value={filters.date_from ?? ""}
          onChange={(e) => setFilters((f) => ({ ...f, date_from: e.target.value || undefined }))}
        />
        <span className="text-xs text-[var(--ink-muted)]">to</span>
        <input
          aria-label="To date"
          type="date"
          className={fieldClass}
          value={filters.date_to ?? ""}
          onChange={(e) => setFilters((f) => ({ ...f, date_to: e.target.value || undefined }))}
        />
      </div>

      <div
        role="group"
        aria-label="Chart timeframe"
        className="ml-auto flex items-center gap-1 rounded-xl border border-[var(--glass-border)] bg-[var(--surface-2)] p-1"
      >
        {TIMEFRAMES.map((tf) => (
          <button
            key={tf.value}
            type="button"
            aria-pressed={filters.timeframe === tf.value}
            onClick={() => setFilters((f) => ({ ...f, timeframe: tf.value }))}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
              filters.timeframe === tf.value
                ? "bg-[var(--accent)] text-white"
                : "text-[var(--ink-muted)] hover:text-[var(--ink-primary)]"
            }`}
          >
            {tf.label}
          </button>
        ))}
      </div>

      {hasActiveFilters && (
        <button
          type="button"
          onClick={onReset}
          className="flex items-center gap-1.5 rounded-xl border border-[var(--glass-border)] px-3 py-2 text-xs font-medium text-[var(--ink-muted)] transition-colors hover:text-[var(--ink-primary)]"
        >
          <IconRefresh />
          Reset
        </button>
      )}
    </div>
  )
}
