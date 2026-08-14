import { useEffect, useMemo, useRef, useState } from "react"
import { backtestApi } from "../../lib/backtestApi"
import type { BacktestRunConfig, ChainSweep, ChainSweepContractResult, OptionUnderlying } from "../../lib/backtestTypes"
import { fmtCurrency, fmtNumber, fmtPercent } from "../../lib/format"

const fieldClass =
  "w-full rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5 text-sm outline-none focus:border-[var(--accent)]"
const labelClass = "mb-1 block text-xs font-medium text-[var(--ink-secondary)]"

type SortKey = "total_pnl" | "win_rate" | "profit_factor" | "total_trades"

interface ChainSweepPanelProps {
  // Reuses the SAME strategy/timeframe/SL-TP/quantity/capital/dates/
  // charges config as the single-contract form above it — a sweep is
  // "the same setup, every contract" not a separately-configured run.
  config: BacktestRunConfig
  sweepId: number | null
  onSweepIdChange: (id: number | null) => void
}

function pnlColor(v: number | null): string {
  if (v === null) return "var(--ink-muted)"
  return v >= 0 ? "var(--status-good)" : "var(--status-critical)"
}

// Chain sweep — run the shared config against EVERY contract for an
// underlying (all strikes x both sides, every expiry unless narrowed to
// one) instead of hand-picking one at a time. Backend does the actual
// work in a background thread (backtest_server.py's /api/backtest/
// options/chain-sweep*, core/domain/chain_sweep.py) since a full chain
// can be hundreds to low thousands of contracts; this just creates it and
// polls for progress.
export function ChainSweepPanel({ config, sweepId, onSweepIdChange }: ChainSweepPanelProps) {
  const [underlyings, setUnderlyings] = useState<OptionUnderlying[]>([])
  const [underlyingFilter, setUnderlyingFilter] = useState("")
  const [selectedUnderlying, setSelectedUnderlying] = useState<OptionUnderlying | null>(null)
  const [expiries, setExpiries] = useState<string[]>([])
  const [selectedExpiry, setSelectedExpiry] = useState<string>("") // "" = every expiry

  const [sweep, setSweep] = useState<ChainSweep | null>(null)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sortKey, setSortKey] = useState<SortKey>("total_pnl")
  const pollRef = useRef<number | null>(null)

  useEffect(() => {
    backtestApi.optionUnderlyings().then(setUnderlyings).catch(() => {})
  }, [])

  useEffect(() => {
    if (!selectedUnderlying) {
      setExpiries([])
      return
    }
    setSelectedExpiry("")
    backtestApi
      .optionExpiries(selectedUnderlying.underlying, selectedUnderlying.category)
      .then(setExpiries)
      .catch(() => setExpiries([]))
  }, [selectedUnderlying])

  // Resume watching an in-flight/finished sweep after a remount (e.g.
  // navigating away and back — see optionsBacktestPageStore.ts's comment
  // on why only the id is persisted, not the whole object).
  useEffect(() => {
    if (sweepId && (!sweep || sweep.id !== sweepId)) {
      backtestApi.getChainSweep(sweepId).then(setSweep).catch(() => {})
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sweepId])

  useEffect(() => {
    if (pollRef.current) window.clearInterval(pollRef.current)
    if (!sweep || sweep.status === "done" || sweep.status === "failed") return

    pollRef.current = window.setInterval(() => {
      backtestApi
        .getChainSweep(sweep.id)
        .then(setSweep)
        .catch(() => {})
    }, 1500)
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sweep?.id, sweep?.status])

  const filteredUnderlyings = useMemo(() => {
    const q = underlyingFilter.trim().toUpperCase()
    if (!q) return underlyings
    return underlyings.filter((u) => u.underlying.includes(q))
  }, [underlyings, underlyingFilter])

  const sortedContracts = useMemo(() => {
    if (!sweep) return []
    const withValue = sweep.contracts.filter((c) => c.status === "done" || c.status === "skipped")
    return [...withValue].sort((a, b) => {
      const av = a[sortKey] ?? -Infinity
      const bv = b[sortKey] ?? -Infinity
      return (bv as number) - (av as number)
    })
  }, [sweep, sortKey])

  async function startSweep() {
    if (!selectedUnderlying || !config.strategy) return
    setStarting(true)
    setError(null)
    try {
      const created = await backtestApi.createChainSweep({
        strategy: config.strategy,
        underlying: selectedUnderlying.underlying,
        category: selectedUnderlying.category,
        expiry: selectedExpiry || undefined,
        timeframe: config.timeframe,
        quantity: config.quantity,
        stoploss_pct: config.stoploss_pct,
        target_pct: config.target_pct,
        trailing_pct: config.trailing_pct,
        max_cycles_per_day: config.max_cycles_per_day,
        start_time: config.start_time,
        end_time: config.end_time,
        capital: config.capital,
        charges: config.charges,
        date_from: config.date_from || undefined,
        date_to: config.date_to || undefined,
      })
      setSweep(created)
      onSweepIdChange(created.id)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't start the sweep.")
    } finally {
      setStarting(false)
    }
  }

  return (
    <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] p-5 backdrop-blur-sm">
      <h2 className="mb-1 text-sm font-semibold text-[var(--ink-primary)]">Sweep Whole Chain</h2>
      <p className="mb-4 text-xs text-[var(--ink-muted)]">
        Runs the strategy/config above against every strike x side for an underlying (every expiry
        unless you pick one), so you don't have to test contracts one at a time. Background job — safe
        to navigate away, come back and it'll still be here.
      </p>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <label>
          <span className={labelClass}>Underlying</span>
          <input
            type="text"
            list="sweep-underlyings"
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
          <datalist id="sweep-underlyings">
            {filteredUnderlyings.map((u) => (
              <option key={`${u.category}:${u.underlying}`} value={u.underlying} />
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
            <option value="">All expiries</option>
            {expiries.map((exp) => (
              <option key={exp} value={exp}>
                {exp}
              </option>
            ))}
          </select>
        </label>

        <div className="flex items-end">
          <button
            onClick={startSweep}
            disabled={starting || !selectedUnderlying || !config.strategy || (!!sweep && sweep.status !== "done" && sweep.status !== "failed")}
            className="w-full rounded-md bg-[var(--accent)] px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50"
          >
            {starting ? "Starting…" : sweep && (sweep.status === "pending" || sweep.status === "running") ? "Running…" : "Sweep Chain"}
          </button>
        </div>
      </div>

      {error && <p className="mt-3 text-xs text-[var(--status-critical)]">{error}</p>}

      {sweep && (
        <div className="mt-5 border-t border-[var(--glass-border)] pt-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-sm">
            <span className="text-[var(--ink-secondary)]">
              {sweep.underlying} — {sweep.status === "running" || sweep.status === "pending"
                ? `${sweep.processed_contracts} / ${sweep.total_contracts} contracts`
                : `${sweep.total_contracts} contracts, ${sweep.status}`}
            </span>
            {sweep.warnings.length > 0 && (
              <span className="text-xs text-[var(--status-critical)]">{sweep.warnings.join("; ")}</span>
            )}
          </div>

          {(sweep.status === "pending" || sweep.status === "running") && (
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--surface-2)]">
              <div
                className="h-full bg-[var(--accent)] transition-all"
                style={{
                  width: `${sweep.total_contracts ? (sweep.processed_contracts / sweep.total_contracts) * 100 : 0}%`,
                }}
              />
            </div>
          )}

          {sweep.status === "failed" && (
            <p className="text-sm text-[var(--status-critical)]">Sweep failed: {sweep.error}</p>
          )}

          {sortedContracts.length > 0 && (
            <div className="mt-4 overflow-x-auto">
              <div className="mb-2 flex gap-1.5">
                {(["total_pnl", "win_rate", "profit_factor", "total_trades"] as SortKey[]).map((k) => (
                  <button
                    key={k}
                    type="button"
                    onClick={() => setSortKey(k)}
                    className={`rounded-md border px-2.5 py-1 text-xs ${
                      sortKey === k
                        ? "border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]"
                        : "border-[var(--border)] bg-[var(--surface-2)] text-[var(--ink-secondary)]"
                    }`}
                  >
                    Sort: {k.replace("_", " ")}
                  </button>
                ))}
              </div>

              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-[var(--ink-muted)]">
                    <th className="py-1.5 pr-3">Contract</th>
                    <th className="py-1.5 pr-3 text-right">Trades</th>
                    <th className="py-1.5 pr-3 text-right">Win Rate</th>
                    <th className="py-1.5 pr-3 text-right">Profit Factor</th>
                    <th className="py-1.5 pr-3 text-right">Net P&L</th>
                    <th className="py-1.5 text-right">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedContracts.map((c: ChainSweepContractResult) => (
                    <tr key={c.symbol} className="border-t border-[var(--glass-border)]">
                      <td className="py-1.5 pr-3 font-mono text-xs">{c.symbol}</td>
                      <td className="py-1.5 pr-3 text-right">{c.total_trades ?? "—"}</td>
                      <td className="py-1.5 pr-3 text-right">{fmtPercent(c.win_rate)}</td>
                      <td className="py-1.5 pr-3 text-right">{fmtNumber(c.profit_factor)}</td>
                      <td className="py-1.5 pr-3 text-right" style={{ color: pnlColor(c.total_pnl) }}>
                        {fmtCurrency(c.total_pnl)}
                      </td>
                      <td className="py-1.5 text-right text-xs text-[var(--ink-muted)]">{c.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
