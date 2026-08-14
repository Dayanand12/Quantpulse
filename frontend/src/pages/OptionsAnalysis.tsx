import { useEffect, useMemo, useState } from "react"
import { ChartCard } from "../components/analytics/ChartCard"
import { EquityCurveChart } from "../components/analytics/EquityCurveChart"
import { MetricsGlossary } from "../components/analytics/MetricsGlossary"
import { StrategyTable } from "../components/analytics/StrategyTable"
import { SummaryCardRow } from "../components/analytics/SummaryCard"
import { TopCandidatesTable } from "../components/analytics/TopCandidatesTable"
import { backtestApi } from "../lib/backtestApi"
import { formatStrategyParams } from "../lib/backtestTypes"
import type { BacktestResultDetail, BacktestResultSummary } from "../lib/backtestTypes"
import { fmtCurrency, fmtNumber, fmtPercent } from "../lib/format"
import {
  COMPOSITE_SCORE_SORT_KEY,
  DEFAULT_TARGET_COUNT,
  NO_SORT_KEY,
  OPTIONS_TRADE_CONFIDENCE_REFERENCE,
  SORT_METRICS,
  computeCompositeScores,
  selectTopCandidates,
  sortResultSummaries,
} from "../lib/topCandidateSelection"
import type { ScoredCandidate } from "../lib/topCandidateSelection"
import type { StrategyInfo } from "../lib/types"

const ALL_OPTION = "__all__"
// topCandidateSelection.ts's DEFAULT_MIN_TRADES (50) is tuned for
// equity's multi-year single-symbol backtests — a single option contract
// only lives a few weeks, so even a working strategy might fire single
// digits of trades on it (confirmed against real data: 983 stored
// contract results for one strategy topped out at 7 trades each). 50
// would silently hide every row with no explanation. 5 is still enough
// to not be pure noise while matching this data's actual scale.
const OPTIONS_DEFAULT_MIN_TRADES = 5

const fieldClass =
  "w-full rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5 text-sm outline-none focus:border-[var(--accent)]"
const labelClass = "mb-1 block text-xs font-medium text-[var(--ink-secondary)]"

function pnlColor(v: number | null): string {
  if (v === null) return "var(--ink-muted)"
  return v >= 0 ? "var(--status-good)" : "var(--status-critical)"
}

// Options counterpart to pages/Analysis.tsx — same underlying stored
// results (backtest_results), but fetched via a server-side-filtered
// endpoint (see backtestApi.optionResults) instead of that page's
// results(strategy), which loads EVERY row for a strategy regardless of
// instrument. Confirmed against real data why that split matters: one
// strategy in this database has 17,391 equity rows (2.2s to load) vs. 983
// option rows for it specifically (0.1s via this page's endpoint).
// Strike/expiry/side render as real columns here instead of being buried
// in one long symbol string.
export function OptionsAnalysis() {
  const [strategies, setStrategies] = useState<StrategyInfo[]>([])
  const [strategy, setStrategy] = useState("")
  const [underlyings, setUnderlyings] = useState<string[]>([])
  const [underlying, setUnderlying] = useState(ALL_OPTION)
  const [results, setResults] = useState<BacktestResultSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [sideFilter, setSideFilter] = useState(ALL_OPTION)
  const [minTradesFilter, setMinTradesFilter] = useState(String(OPTIONS_DEFAULT_MIN_TRADES))
  const [sortMetric, setSortMetric] = useState(NO_SORT_KEY)

  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<BacktestResultDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const [targetCount, setTargetCount] = useState(String(DEFAULT_TARGET_COUNT))
  const [topCandidates, setTopCandidates] = useState<ScoredCandidate[] | null>(null)
  const [topCandidatesConsidered, setTopCandidatesConsidered] = useState(0)
  const [exportingTop, setExportingTop] = useState(false)
  const [exportTopError, setExportTopError] = useState<string | null>(null)

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
    setUnderlying(ALL_OPTION)
    setSideFilter(ALL_OPTION)
    setSelectedId(null)
    setDetail(null)
    setSortMetric(NO_SORT_KEY)
    backtestApi.optionResultUnderlyings(strategy).then(setUnderlyings).catch(() => setUnderlyings([]))
  }, [strategy])

  useEffect(() => {
    if (!strategy) return
    setLoading(true)
    setSelectedId(null)
    setDetail(null)
    backtestApi
      .optionResults(strategy, underlying === ALL_OPTION ? undefined : underlying)
      .then(setResults)
      .catch(() => setLoadError("Failed to load stored option results."))
      .finally(() => setLoading(false))
  }, [strategy, underlying])

  useEffect(() => {
    if (selectedId === null) {
      setDetail(null)
      return
    }
    setDetailLoading(true)
    backtestApi
      .resultDetail(selectedId)
      .then(setDetail)
      .catch(() => setLoadError("Failed to load that result."))
      .finally(() => setDetailLoading(false))
  }, [selectedId])

  const filteredResults = useMemo(() => {
    const minTrades = minTradesFilter === "" ? null : Number(minTradesFilter)
    const filtered = results.filter(
      (r) =>
        (sideFilter === ALL_OPTION || r.option_side === sideFilter) &&
        (minTrades === null || r.total_trades >= minTrades),
    )
    return sortResultSummaries(filtered, sortMetric)
  }, [results, sideFilter, minTradesFilter, sortMetric])

  const compositeScores = useMemo(
    () => (sortMetric === COMPOSITE_SCORE_SORT_KEY ? computeCompositeScores(filteredResults) : null),
    [sortMetric, filteredResults],
  )

  useEffect(() => {
    setTopCandidates(null)
    setTopCandidatesConsidered(0)
  }, [filteredResults])

  function handleSelectTopCandidates() {
    const n = Number(targetCount)
    const { candidates, consideredCount } = selectTopCandidates(
      filteredResults,
      Number.isFinite(n) && n > 0 ? n : DEFAULT_TARGET_COUNT,
      OPTIONS_TRADE_CONFIDENCE_REFERENCE,
    )
    setTopCandidates(candidates)
    setTopCandidatesConsidered(consideredCount)
  }

  async function handleExportTopCandidates() {
    if (!topCandidates || topCandidates.length === 0) return
    setExportingTop(true)
    setExportTopError(null)
    try {
      const blob = await backtestApi.exportSelectedResultsExcel(topCandidates.map((c) => c.result.id))
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `${strategy}_options_top_${topCandidates.length}_candidates.xlsx`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setExportTopError(e instanceof Error ? e.message : "Failed to export.")
    } finally {
      setExportingTop(false)
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
        <h1 className="text-2xl font-semibold">Options Analysis</h1>
        <p className="mt-1 text-sm text-[var(--ink-muted)]">
          Every option backtest ever logged for a strategy (single runs and chain sweeps alike) —
          strike/expiry/side as real columns, filtered server-side so a strategy with thousands of swept
          contracts stays fast to browse.
        </p>
      </div>

      <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] p-5 backdrop-blur-sm">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
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
            <span className={labelClass}>Underlying</span>
            <select className={fieldClass} value={underlying} onChange={(e) => setUnderlying(e.target.value)}>
              <option value={ALL_OPTION}>All ({underlyings.length})</option>
              {underlyings.map((u) => (
                <option key={u} value={u}>
                  {u}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span className={labelClass}>Side</span>
            <select className={fieldClass} value={sideFilter} onChange={(e) => setSideFilter(e.target.value)}>
              <option value={ALL_OPTION}>All</option>
              <option value="CE">CE</option>
              <option value="PE">PE</option>
            </select>
          </label>
        </div>

        {results.length > 0 && (
          <div className="mt-4 grid grid-cols-2 gap-3 border-t border-[var(--glass-border)] pt-4 sm:grid-cols-3">
            <label>
              <span className={labelClass}>Min Trades</span>
              <input
                type="number"
                min={0}
                className={fieldClass}
                value={minTradesFilter}
                onChange={(e) => setMinTradesFilter(e.target.value)}
                placeholder="No minimum"
                title="Hide contracts with too few trades to trust their metrics"
              />
            </label>

            <label>
              <span className={labelClass}>Sort By</span>
              <select className={fieldClass} value={sortMetric} onChange={(e) => setSortMetric(e.target.value)}>
                <option value={NO_SORT_KEY}>None (as tested)</option>
                <option value={COMPOSITE_SCORE_SORT_KEY}>Composite Score (recommended)</option>
                {SORT_METRICS.map((m) => (
                  <option key={m.key} value={m.key}>
                    {m.label} ({m.direction === "desc" ? "best first" : "lowest first"})
                  </option>
                ))}
              </select>
            </label>

            <div className="flex items-end gap-2">
              <label className="flex-1">
                <span className={labelClass}>Target Count</span>
                <input
                  type="number"
                  min={1}
                  className={fieldClass}
                  value={targetCount}
                  onChange={(e) => setTargetCount(e.target.value)}
                />
              </label>
              <button
                type="button"
                onClick={handleSelectTopCandidates}
                disabled={filteredResults.length === 0}
                className="shrink-0 rounded-md bg-[var(--accent)] px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50"
              >
                Select Top {targetCount || DEFAULT_TARGET_COUNT}
              </button>
            </div>
          </div>
        )}
      </div>

      {topCandidates && (
        <TopCandidatesTable
          candidates={topCandidates}
          consideredCount={topCandidatesConsidered}
          onExport={handleExportTopCandidates}
          exporting={exportingTop}
          exportError={exportTopError}
        />
      )}

      {loading && <p className="text-sm text-[var(--ink-muted)]">Loading…</p>}

      {!loading && results.length === 0 && (
        <p className="text-sm text-[var(--ink-muted)]">
          No stored option results for this strategy yet — run a backtest or a chain sweep from the
          Options Backtest page first.
        </p>
      )}

      {!loading && results.length > 0 && filteredResults.length === 0 && (
        <p className="text-sm text-[var(--ink-muted)]">
          {results.length} stored result{results.length === 1 ? "" : "s"}, but none match the current
          filters — try lowering Min Trades (a single contract's whole lifespan is a few weeks, so trade
          counts run much lower than equity's multi-year backtests).
        </p>
      )}

      {!loading && filteredResults.length > 0 && (
        <div className="overflow-x-auto rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] p-5 backdrop-blur-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-[var(--ink-muted)]">
                <th className="py-1.5 pr-3">Underlying</th>
                <th className="py-1.5 pr-3">Strike</th>
                <th className="py-1.5 pr-3">Side</th>
                <th className="py-1.5 pr-3">Expiry</th>
                <th className="py-1.5 pr-3 text-right">Trades</th>
                <th className="py-1.5 pr-3 text-right">Win Rate</th>
                <th className="py-1.5 pr-3 text-right">Profit Factor</th>
                <th className="py-1.5 pr-3 text-right">Net P&L</th>
                {sortMetric === COMPOSITE_SCORE_SORT_KEY && <th className="py-1.5 text-right">Score</th>}
              </tr>
            </thead>
            <tbody>
              {filteredResults.map((r) => (
                <tr
                  key={r.id}
                  onClick={() => setSelectedId(r.id)}
                  className={`cursor-pointer border-t border-[var(--glass-border)] hover:bg-[var(--surface-2)] ${
                    selectedId === r.id ? "bg-[var(--surface-2)]" : ""
                  }`}
                >
                  <td className="py-1.5 pr-3">{r.option_underlying}</td>
                  <td className="py-1.5 pr-3">{r.option_strike}</td>
                  <td className="py-1.5 pr-3">{r.option_side}</td>
                  <td className="py-1.5 pr-3 text-xs text-[var(--ink-muted)]">{r.option_expiry}</td>
                  <td className="py-1.5 pr-3 text-right">{r.total_trades}</td>
                  <td className="py-1.5 pr-3 text-right">{fmtPercent(r.win_rate)}</td>
                  <td className="py-1.5 pr-3 text-right">{fmtNumber(r.profit_factor)}</td>
                  <td className="py-1.5 pr-3 text-right" style={{ color: pnlColor(r.total_pnl) }}>
                    {fmtCurrency(r.total_pnl)}
                  </td>
                  {sortMetric === COMPOSITE_SCORE_SORT_KEY && (
                    <td className="py-1.5 text-right">
                      {compositeScores?.get(r.id) != null ? compositeScores.get(r.id)!.toFixed(2) : "—"}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {detailLoading && <p className="text-sm text-[var(--ink-muted)]">Loading detail…</p>}

      {!detailLoading && detail && (
        <div className="flex flex-col gap-6">
          <div className="rounded-lg border border-[var(--glass-border)] bg-[var(--glass-surface)] px-4 py-3 text-sm text-[var(--ink-secondary)]">
            {detail.summary.symbols} · {detail.summary.date_from} → {detail.summary.date_to} ·{" "}
            {detail.summary.timeframe} · SL {detail.summary.stoploss_pct}% / TP {detail.summary.target_pct}% /
            Trail {detail.summary.trailing_pct}% · {detail.summary.charges_enabled ? "with" : "without"} charges
          </div>

          {detail.summary.strategy_params_json && (
            <div className="rounded-lg border border-[var(--glass-border)] bg-[var(--glass-surface)] px-4 py-3">
              <div className="text-xs font-medium text-[var(--ink-secondary)]">Indicator parameters used</div>
              <div className="mt-1 text-sm text-[var(--ink-primary)]">
                {formatStrategyParams(detail.summary.strategy_params_json) || "(no named parameters)"}
              </div>
            </div>
          )}

          <SummaryCardRow metrics={detail.result.metrics} />
          <MetricsGlossary />

          <ChartCard title="Equity Curve" subtitle="Cumulative P&L across every closed trade in this run">
            <EquityCurveChart points={detail.result.equity_curve ?? []} />
          </ChartCard>

          <StrategyTable
            rows={detail.result.by_market_condition ?? []}
            title="By Market Condition"
            firstColumnLabel="Condition"
            searchPlaceholder="Search conditions…"
          />
        </div>
      )}
    </div>
  )
}
