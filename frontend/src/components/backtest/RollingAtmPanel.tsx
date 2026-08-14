import { useEffect, useMemo, useState } from "react"
import { ChartCard } from "../analytics/ChartCard"
import { EquityCurveChart } from "../analytics/EquityCurveChart"
import { StrategyTable } from "../analytics/StrategyTable"
import { SummaryCardRow } from "../analytics/SummaryCard"
import { backtestApi } from "../../lib/backtestApi"
import type { BacktestRunConfig, BacktestRunResult, OptionUnderlying } from "../../lib/backtestTypes"
import { fmtCurrency } from "../../lib/format"

const fieldClass =
  "w-full rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5 text-sm outline-none focus:border-[var(--accent)]"
const labelClass = "mb-1 block text-xs font-medium text-[var(--ink-secondary)]"

interface RollingAtmPanelProps {
  // Same shared risk/sizing config as the single-contract form and the
  // chain-sweep panel above it on this page.
  config: BacktestRunConfig
}

// Rolling ATM — the realistic counterpart to "Sweep Whole Chain" above:
// that panel finds which historical contract performed best (useful for
// spotting patterns, not directly tradeable, since that exact contract
// won't exist again); this rolls through every expiry in order and picks
// whichever strike is closest to spot AT THAT MOMENT, held to expiry then
// re-selected — the same information a real trader would actually have
// had. Synchronous (unlike the sweep) since one underlying's full roll is
// only ~20 single-contract backtests, one per expiry.
export function RollingAtmPanel({ config }: RollingAtmPanelProps) {
  const [underlyings, setUnderlyings] = useState<OptionUnderlying[]>([])
  const [underlyingFilter, setUnderlyingFilter] = useState("")
  const [selectedUnderlying, setSelectedUnderlying] = useState<OptionUnderlying | null>(null)
  const [side, setSide] = useState<"CE" | "PE">("CE")

  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<BacktestRunResult | null>(null)

  useEffect(() => {
    backtestApi.optionUnderlyings().then(setUnderlyings).catch(() => {})
  }, [])

  const filteredUnderlyings = useMemo(() => {
    const q = underlyingFilter.trim().toUpperCase()
    if (!q) return underlyings
    return underlyings.filter((u) => u.underlying.includes(q))
  }, [underlyings, underlyingFilter])

  async function handleRun() {
    if (!selectedUnderlying || !config.strategy) return
    setRunning(true)
    setError(null)
    try {
      const res = await backtestApi.runRollingAtm({
        strategy: config.strategy,
        underlying: selectedUnderlying.underlying,
        category: selectedUnderlying.category,
        side,
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
      setResult(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Rolling ATM backtest failed.")
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] p-5 backdrop-blur-sm">
      <h2 className="mb-1 text-sm font-semibold text-[var(--ink-primary)]">Rolling ATM Backtest</h2>
      <p className="mb-4 text-xs text-[var(--ink-muted)]">
        Rolls through every expiry in order — held to expiry, then re-picks whichever strike is closest
        to spot at that moment. Realistic (no hindsight), unlike sweeping the whole chain above.
      </p>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <label>
          <span className={labelClass}>Underlying</span>
          <input
            type="text"
            list="rolling-atm-underlyings"
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
          <datalist id="rolling-atm-underlyings">
            {filteredUnderlyings.map((u) => (
              <option key={`${u.category}:${u.underlying}`} value={u.underlying} />
            ))}
          </datalist>
        </label>

        <label>
          <span className={labelClass}>Side</span>
          <div className="flex gap-1.5">
            {(["CE", "PE"] as const).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setSide(s)}
                className={`flex-1 rounded-md border px-3 py-1.5 text-sm ${
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

        <div className="col-span-2 flex items-end">
          <button
            onClick={handleRun}
            disabled={running || !selectedUnderlying || !config.strategy}
            className="w-full rounded-md bg-[var(--accent)] px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50"
          >
            {running ? "Rolling…" : "Run Rolling ATM"}
          </button>
        </div>
      </div>

      {error && <p className="mt-3 text-xs text-[var(--status-critical)]">{error}</p>}

      {result && (
        <div className="mt-5 flex flex-col gap-5 border-t border-[var(--glass-border)] pt-4">
          <div className="rounded-lg border border-[var(--glass-border)] bg-[var(--surface-2)] px-4 py-3 text-sm text-[var(--ink-secondary)]">
            {result.symbols_used.join(", ")} · {result.total_trades} trades across{" "}
            {(result.roll_log ?? []).filter((r) => r.symbol).length} rolls
          </div>

          {(result.warnings ?? []).length > 0 && (
            <div className="rounded-lg border border-[var(--status-critical)]/40 bg-[var(--status-critical)]/10 px-4 py-3 text-sm text-[var(--status-critical)]">
              {(result.warnings ?? []).map((w) => (
                <p key={w}>{w}</p>
              ))}
            </div>
          )}

          <SummaryCardRow metrics={result.metrics} />

          <ChartCard title="Equity Curve" subtitle="Cumulative P&L across every roll, concatenated in time order">
            <EquityCurveChart points={result.equity_curve} />
          </ChartCard>

          {result.roll_log && result.roll_log.length > 0 && (
            <div className="overflow-x-auto rounded-lg border border-[var(--glass-border)]">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-[var(--surface-2)] text-left text-xs text-[var(--ink-muted)]">
                    <th className="px-3 py-1.5">Expiry</th>
                    <th className="px-3 py-1.5">Contract Picked</th>
                    <th className="px-3 py-1.5 text-right">Strike</th>
                    <th className="px-3 py-1.5 text-right">Spot at Roll</th>
                    <th className="px-3 py-1.5">Note</th>
                  </tr>
                </thead>
                <tbody>
                  {result.roll_log.map((r) => (
                    <tr key={r.expiry} className="border-t border-[var(--glass-border)]">
                      <td className="px-3 py-1.5">{r.expiry}</td>
                      <td className="px-3 py-1.5 font-mono text-xs">{r.symbol ?? "—"}</td>
                      <td className="px-3 py-1.5 text-right">{r.strike ?? "—"}</td>
                      <td className="px-3 py-1.5 text-right">{r.spot_at_roll != null ? fmtCurrency(r.spot_at_roll) : "—"}</td>
                      <td className="px-3 py-1.5 text-xs text-[var(--ink-muted)]">{r.note}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <StrategyTable
            rows={result.by_symbol}
            title="By Contract — which specific rolls this worked on"
            firstColumnLabel="Contract"
            searchPlaceholder="Search…"
          />

          {result.by_oi_level.length > 0 && (
            <StrategyTable
              rows={result.by_oi_level}
              title="By OI Level — open interest at entry, split into thirds for this run"
              firstColumnLabel="OI Level"
              searchPlaceholder="Search…"
            />
          )}
        </div>
      )}
    </div>
  )
}
