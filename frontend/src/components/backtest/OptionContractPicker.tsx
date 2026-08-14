import { useEffect, useMemo, useState } from "react"
import { backtestApi } from "../../lib/backtestApi"
import type { OptionContractInfo, OptionUnderlying } from "../../lib/backtestTypes"

const fieldClass =
  "w-full rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5 text-sm outline-none focus:border-[var(--accent)]"
const labelClass = "mb-1 block text-xs font-medium text-[var(--ink-secondary)]"

interface OptionContractPickerProps {
  // The currently-selected contract's OptionContract.symbol string (e.g.
  // "RELIANCE:1600CE:2026-01-27"), or "" if nothing's picked yet — same
  // convention as the rest of the options backtest form, which just needs
  // this one string for /api/backtest/run's `symbols`.
  value: string
  onChange: (symbol: string) => void
}

// Three narrowing selects — underlying, then expiry, then strike/side —
// backed by backtest_server.py's /api/backtest/options/* endpoints, which
// read historical_data_dir/options/{stocks,index}/ directly (see
// Data_ingestion/options_ingest_stock.py / options_ingest_index.py).
// Deliberately manual selection only, no auto-ATM/rolling logic — see the
// project's Phase 4 scope decision (this app's options-backtesting plan).
export function OptionContractPicker({ value, onChange }: OptionContractPickerProps) {
  const [underlyings, setUnderlyings] = useState<OptionUnderlying[]>([])
  const [underlyingFilter, setUnderlyingFilter] = useState("")
  const [selectedUnderlying, setSelectedUnderlying] = useState<OptionUnderlying | null>(null)

  const [expiries, setExpiries] = useState<string[]>([])
  const [selectedExpiry, setSelectedExpiry] = useState<string>("")

  const [contracts, setContracts] = useState<OptionContractInfo[]>([])
  const [side, setSide] = useState<"CE" | "PE">("CE")
  const [selectedStrike, setSelectedStrike] = useState<number | "">("")

  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    backtestApi
      .optionUnderlyings()
      .then(setUnderlyings)
      .catch(() => setLoadError("Couldn't load the underlying list — is run_backtest_server.py running?"))
  }, [])

  useEffect(() => {
    if (!selectedUnderlying) {
      setExpiries([])
      return
    }
    setSelectedExpiry("")
    setContracts([])
    setSelectedStrike("")
    backtestApi
      .optionExpiries(selectedUnderlying.underlying, selectedUnderlying.category)
      .then(setExpiries)
      .catch(() => setLoadError(`Couldn't load expiries for ${selectedUnderlying.underlying}.`))
  }, [selectedUnderlying])

  useEffect(() => {
    if (!selectedUnderlying || !selectedExpiry) {
      setContracts([])
      return
    }
    setSelectedStrike("")
    backtestApi
      .optionContracts(selectedUnderlying.underlying, selectedUnderlying.category, selectedExpiry)
      .then(setContracts)
      .catch(() => setLoadError(`Couldn't load contracts for ${selectedUnderlying.underlying} ${selectedExpiry}.`))
  }, [selectedUnderlying, selectedExpiry])

  const strikesForSide = useMemo(
    () =>
      contracts
        .filter((c) => c.side === side)
        .map((c) => c.strike)
        .sort((a, b) => a - b),
    [contracts, side],
  )

  const filteredUnderlyings = useMemo(() => {
    const q = underlyingFilter.trim().toUpperCase()
    if (!q) return underlyings
    return underlyings.filter((u) => u.underlying.includes(q))
  }, [underlyings, underlyingFilter])

  useEffect(() => {
    if (selectedStrike === "") return
    const contract = contracts.find((c) => c.strike === selectedStrike && c.side === side)
    onChange(contract?.symbol ?? "")
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedStrike, side, contracts])

  if (loadError) {
    return <p className="text-sm text-[var(--status-critical)]">{loadError}</p>
  }

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      <label>
        <span className={labelClass}>Underlying</span>
        <input
          type="text"
          list="option-underlyings"
          placeholder="e.g. RELIANCE, NIFTY"
          value={underlyingFilter || selectedUnderlying?.underlying || ""}
          onChange={(e) => {
            setUnderlyingFilter(e.target.value)
            const match = underlyings.find(
              (u) => u.underlying.toUpperCase() === e.target.value.trim().toUpperCase(),
            )
            setSelectedUnderlying(match ?? null)
          }}
          className={fieldClass}
        />
        <datalist id="option-underlyings">
          {filteredUnderlyings.map((u) => (
            <option key={`${u.category}:${u.underlying}`} value={u.underlying}>
              {u.category === "index" ? "index" : ""}
            </option>
          ))}
        </datalist>
      </label>

      <label>
        <span className={labelClass}>Expiry</span>
        <select
          className={fieldClass}
          value={selectedExpiry}
          onChange={(e) => setSelectedExpiry(e.target.value)}
          disabled={!selectedUnderlying}
        >
          <option value="">{selectedUnderlying ? "Pick expiry…" : "Pick underlying first"}</option>
          {expiries.map((e) => (
            <option key={e} value={e}>
              {e}
            </option>
          ))}
        </select>
      </label>

      <label>
        <span className={labelClass}>Side</span>
        <div className="flex gap-1.5">
          {(["CE", "PE"] as const).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setSide(s)}
              disabled={!selectedExpiry}
              className={`flex-1 rounded-md border px-3 py-1.5 text-sm disabled:opacity-50 ${
                side === s
                  ? "border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]"
                  : "border-[var(--border)] bg-[var(--surface-2)] text-[var(--ink-secondary)]"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </label>

      <label>
        <span className={labelClass}>Strike</span>
        <select
          className={fieldClass}
          value={selectedStrike}
          onChange={(e) => setSelectedStrike(e.target.value ? Number(e.target.value) : "")}
          disabled={!selectedExpiry}
        >
          <option value="">{selectedExpiry ? "Pick strike…" : "Pick expiry first"}</option>
          {strikesForSide.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
      </label>

      {value && (
        <p className="col-span-full text-xs text-[var(--ink-muted)]">
          Selected contract: <span className="font-medium text-[var(--ink-secondary)]">{value}</span>
        </p>
      )}
    </div>
  )
}
