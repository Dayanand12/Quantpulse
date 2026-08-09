import { useEffect, useState } from "react"
import { BacktestComparisonChart } from "../components/analytics/BacktestComparisonChart"
import { ChartCard } from "../components/analytics/ChartCard"
import { EquityCurveChart } from "../components/analytics/EquityCurveChart"
import { StrategyTable } from "../components/analytics/StrategyTable"
import { SummaryCardRow } from "../components/analytics/SummaryCard"
import { backtestApi } from "../lib/backtestApi"
import { formatStrategyParams } from "../lib/backtestTypes"
import type { BacktestResultDetail, BacktestResultSummary } from "../lib/backtestTypes"
import type { StrategyInfo } from "../lib/types"

const ALL_OPTION = "__all__"

const fieldClass =
  "w-full rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5 text-sm outline-none focus:border-[var(--accent)]"
const labelClass = "mb-1 block text-xs font-medium text-[var(--ink-secondary)]"

function comboLabel(r: BacktestResultSummary): string {
  const paramsPart = formatStrategyParams(r.strategy_params_json)
  return (
    `${r.timeframe} · SL ${r.stoploss_pct} / TP ${r.target_pct} / Trail ${r.trailing_pct}` +
    (paramsPart ? ` · ${paramsPart}` : "") +
    ` · ${r.date_from}→${r.date_to} · ${r.symbols === "WATCHLIST" ? "Watchlist" : r.symbols}`
  )
}

export function Analysis() {
  const [strategies, setStrategies] = useState<StrategyInfo[]>([])
  const [strategy, setStrategy] = useState("")
  const [results, setResults] = useState<BacktestResultSummary[]>([])
  const [selection, setSelection] = useState<string>(ALL_OPTION)
  const [detail, setDetail] = useState<BacktestResultDetail | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  useEffect(() => {
    backtestApi
      .strategies()
      .then((list) => {
        setStrategies(list)
        if (list.length > 0) setStrategy(list[0].name)
      })
      .catch(() => setLoadError("Couldn't reach the backtest server. Is `python run_backtest_server.py` running?"))
  }, [])

  useEffect(() => {
    if (!strategy) return
    setLoading(true)
    setDetail(null)
    setSelection(ALL_OPTION)
    backtestApi
      .results(strategy)
      .then(setResults)
      .catch(() => setLoadError("Failed to load stored backtest results."))
      .finally(() => setLoading(false))
  }, [strategy])

  useEffect(() => {
    if (selection === ALL_OPTION) {
      setDetail(null)
      return
    }
    const id = Number(selection)
    setLoading(true)
    backtestApi
      .resultDetail(id)
      .then(setDetail)
      .catch(() => setLoadError("Failed to load that result."))
      .finally(() => setLoading(false))
  }, [selection])

  async function handleDeleteResult() {
    if (selection === ALL_OPTION) return
    const id = Number(selection)
    setDeleting(true)
    setDeleteError(null)
    try {
      await backtestApi.deleteResult(id)
      const refreshed = await backtestApi.results(strategy)
      setResults(refreshed)
      setSelection(ALL_OPTION)
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : "Failed to delete that result.")
    } finally {
      setDeleting(false)
    }
  }

  if (loadError) {
    return (
      <div className="rounded-2xl border border-[var(--status-critical)]/40 bg-[var(--glass-surface)] p-5 text-sm text-[var(--status-critical)]">
        {loadError}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Analysis</h1>
        <p className="mt-1 text-sm text-[var(--ink-muted)]">
          Every backtest run gets logged automatically (see the Backtest tab) — pick a strategy and
          browse everything that's been tested on it, instead of tracking results in a spreadsheet.
        </p>
      </div>

      <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] p-5 backdrop-blur-sm">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label>
            <span className={labelClass}>Strategy</span>
            <select className={fieldClass} value={strategy} onChange={(e) => setStrategy(e.target.value)}>
              {strategies.length === 0 && <option value="">Loading…</option>}
              {strategies.map((s) => (
                <option key={s.name} value={s.name}>
                  {s.display_name}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span className={labelClass}>Tested Combination</span>
            <select className={fieldClass} value={selection} onChange={(e) => setSelection(e.target.value)}>
              <option value={ALL_OPTION}>All ({results.length}) — compare</option>
              {results.map((r) => (
                <option key={r.id} value={r.id}>
                  {comboLabel(r)}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {loading && <p className="text-sm text-[var(--ink-muted)]">Loading…</p>}

      {!loading && selection === ALL_OPTION && (
        <ChartCard
          title="Parameter Comparison"
          subtitle="Every stored run for this strategy — click a bar (or pick it above) to see its full breakdown"
        >
          <BacktestComparisonChart
            results={results}
            selectedId={null}
            onSelect={(id) => setSelection(String(id))}
          />
        </ChartCard>
      )}

      {!loading && selection !== ALL_OPTION && detail && (
        <div className="flex flex-col gap-6">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[var(--glass-border)] bg-[var(--glass-surface)] px-4 py-3 text-sm text-[var(--ink-secondary)]">
            <div>
              {detail.summary.symbols === "WATCHLIST" ? "Whole watchlist" : detail.summary.symbols} ·{" "}
              {detail.summary.date_from} → {detail.summary.date_to} · {detail.summary.timeframe} · SL{" "}
              {detail.summary.stoploss_pct}% / TP {detail.summary.target_pct}% / Trail{" "}
              {detail.summary.trailing_pct}% · {detail.summary.charges_enabled ? "with" : "without"} charges
              {detail.summary.created_at && (
                <span className="ml-2 text-[var(--ink-muted)]">
                  logged {new Date(detail.summary.created_at).toLocaleString("en-IN")}
                </span>
              )}
            </div>
            <button
              type="button"
              onClick={handleDeleteResult}
              disabled={deleting}
              title="Delete this stored combination — the underlying strategy is untouched"
              className="shrink-0 rounded-md border border-[var(--status-critical)]/40 px-2.5 py-1 text-xs text-[var(--status-critical)] hover:bg-[var(--status-critical)]/10 disabled:opacity-50"
            >
              {deleting ? "Deleting…" : "Delete this combination"}
            </button>
          </div>
          {deleteError && <p className="text-xs text-[var(--status-critical)]">{deleteError}</p>}

          {detail.summary.strategy_params_json && (
            <div className="rounded-lg border border-[var(--glass-border)] bg-[var(--glass-surface)] px-4 py-3">
              <div className="text-xs font-medium text-[var(--ink-secondary)]">
                Indicator parameters used for this run
              </div>
              <div className="mt-1 text-sm text-[var(--ink-primary)]">
                {formatStrategyParams(detail.summary.strategy_params_json) || "(no named parameters)"}
              </div>
              <details className="mt-2">
                <summary className="cursor-pointer text-xs text-[var(--ink-muted)] hover:text-[var(--ink-primary)]">
                  View raw conditions.json
                </summary>
                <pre className="mt-2 max-h-64 overflow-auto rounded-md bg-[var(--surface-2)] p-3 text-xs">
                  {JSON.stringify(JSON.parse(detail.summary.strategy_params_json), null, 2)}
                </pre>
              </details>
            </div>
          )}

          <SummaryCardRow metrics={detail.result.metrics} />

          <ChartCard title="Equity Curve" subtitle="Cumulative P&L across every closed trade in this run">
            <EquityCurveChart points={detail.result.equity_curve} />
          </ChartCard>

          <StrategyTable
            rows={detail.result.by_symbol}
            title="By Symbol"
            firstColumnLabel="Symbol"
            searchPlaceholder="Search symbols…"
          />
          <StrategyTable
            rows={detail.result.by_market_condition}
            title="By Market Condition"
            firstColumnLabel="Condition"
            searchPlaceholder="Search conditions…"
          />
        </div>
      )}
    </div>
  )
}
