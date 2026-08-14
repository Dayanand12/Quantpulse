import { useEffect, useMemo, useState } from "react"
import { BacktestComparisonChart } from "../components/analytics/BacktestComparisonChart"
import { ChartCard } from "../components/analytics/ChartCard"
import { EquityCurveChart } from "../components/analytics/EquityCurveChart"
import { MetricsGlossary } from "../components/analytics/MetricsGlossary"
import { StrategyTable } from "../components/analytics/StrategyTable"
import { SummaryCardRow } from "../components/analytics/SummaryCard"
import { TopCandidatesTable } from "../components/analytics/TopCandidatesTable"
import { backtestApi } from "../lib/backtestApi"
import { formatStrategyParams } from "../lib/backtestTypes"
import type {
  BacktestResultDetail,
  BacktestResultSummary,
  BacktestRunResult,
  NamedWatchlist,
} from "../lib/backtestTypes"
import {
  DEFAULT_MIN_TRADES,
  DEFAULT_TARGET_COUNT,
  computeCompositeScores,
  selectTopCandidates,
} from "../lib/topCandidateSelection"
import type { ScoredCandidate } from "../lib/topCandidateSelection"
import type { CandleTimeframe, StrategyInfo } from "../lib/types"

// Everything about one stored run in a single self-contained object — the
// strategy's actual conditions.json plus what it was tested with plus how
// it performed, so pasting this whole thing into an LLM for tuning
// research doesn't need three separate copies from three separate places.
function buildResearchBlob(detail: BacktestResultDetail): object {
  let conditions: unknown = null
  if (detail.summary.strategy_params_json) {
    try {
      conditions = JSON.parse(detail.summary.strategy_params_json)
    } catch {
      conditions = detail.summary.strategy_params_json // malformed JSON — still worth including raw
    }
  }
  return {
    strategy: detail.summary.strategy_name,
    symbols: detail.summary.symbols,
    date_from: detail.summary.date_from,
    date_to: detail.summary.date_to,
    timeframe: detail.summary.timeframe,
    quantity: detail.summary.quantity,
    stoploss_pct: detail.summary.stoploss_pct,
    target_pct: detail.summary.target_pct,
    trailing_pct: detail.summary.trailing_pct,
    max_cycles_per_day: detail.summary.max_cycles_per_day,
    start_time: detail.summary.start_time,
    end_time: detail.summary.end_time,
    charges_enabled: detail.summary.charges_enabled,
    strategy_conditions: conditions,
    metrics: detail.result.metrics,
  }
}

const ALL_OPTION = "__all__"
const NO_SORT = "__none__"

const fieldClass =
  "w-full rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5 text-sm outline-none focus:border-[var(--accent)]"
const labelClass = "mb-1 block text-xs font-medium text-[var(--ink-secondary)]"

function comboLabel(r: BacktestResultSummary, score?: number | null): string {
  const paramsPart = formatStrategyParams(r.strategy_params_json)
  return (
    `${r.timeframe} · SL ${r.stoploss_pct} / TP ${r.target_pct} / Trail ${r.trailing_pct}` +
    (paramsPart ? ` · ${paramsPart}` : "") +
    ` · ${r.date_from}→${r.date_to} · ${symbolsLabel(r.symbols)}` +
    (score != null ? ` · Score ${score.toFixed(2)}` : "")
  )
}

function symbolsLabel(symbols: string): string {
  return symbols === "WATCHLIST" ? "Whole watchlist" : symbols
}

// Sort direction is fixed per metric rather than user-toggled — "best
// first" means something different for each (higher win rate is better,
// lower drawdown is better), and a single asc/desc toggle applied
// uniformly would silently show the WORST combo first for drawdown.
const SORT_METRICS: { key: keyof BacktestResultSummary; label: string; direction: "asc" | "desc" }[] = [
  { key: "win_rate", label: "Win Rate", direction: "desc" },
  { key: "profit_factor", label: "Profit Factor", direction: "desc" },
  { key: "total_pnl", label: "Total P&L", direction: "desc" },
  { key: "sharpe_ratio", label: "Sharpe Ratio", direction: "desc" },
  { key: "max_drawdown_pct", label: "Max Drawdown %", direction: "asc" },
  { key: "total_trades", label: "Total Trades", direction: "desc" },
]

// Composite Score, Stability Score, diversity filtering and the Top-N
// selection pipeline all live in lib/topCandidateSelection.ts (pure, no
// React) — this page just wires the UI to it. See that file for the full
// design writeup.
const COMPOSITE_SCORE_KEY = "__composite__"

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
  const [copied, setCopied] = useState(false)
  const [copyError, setCopyError] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)
  const [exportingFiltered, setExportingFiltered] = useState(false)
  const [exportFilteredError, setExportFilteredError] = useState<string | null>(null)

  const [symbolsFilter, setSymbolsFilter] = useState(ALL_OPTION)
  const [timeframeFilter, setTimeframeFilter] = useState(ALL_OPTION)
  const [slFilter, setSlFilter] = useState(ALL_OPTION)
  const [trailFilter, setTrailFilter] = useState(ALL_OPTION)
  const [sortMetric, setSortMetric] = useState(NO_SORT)
  // Gates the composite score (and the Top-N selection) away from
  // low-sample-size combos where a metric like profit factor is mostly
  // noise (e.g. 2 wins out of 3 trades) rather than a real edge. "" = no
  // minimum. Defaults to 50, matching the Top-N selection's own default.
  const [minTradesFilter, setMinTradesFilter] = useState(String(DEFAULT_MIN_TRADES))

  const [targetCount, setTargetCount] = useState(String(DEFAULT_TARGET_COUNT))
  const [topCandidates, setTopCandidates] = useState<ScoredCandidate[] | null>(null)
  const [topCandidatesConsidered, setTopCandidatesConsidered] = useState(0)
  const [exportingTop, setExportingTop] = useState(false)
  const [exportTopError, setExportTopError] = useState<string | null>(null)

  // Results are now stored one-per-symbol (see runners/backtesting/
  // result_persistence.py::save_per_symbol_results) — this cross-
  // references a watchlist's CURRENT members against each row's `symbols`
  // (which is just one symbol for anything saved after that change shipped)
  // so "show me this watchlist's results" doesn't need the symbol-to-
  // watchlist link to be stored anywhere.
  const [namedWatchlists, setNamedWatchlists] = useState<NamedWatchlist[]>([])
  const [watchlistFilter, setWatchlistFilter] = useState(ALL_OPTION)

  const [combinedView, setCombinedView] = useState<BacktestRunResult | null>(null)
  const [combinedViewLoading, setCombinedViewLoading] = useState(false)
  const [combinedViewError, setCombinedViewError] = useState<string | null>(null)

  useEffect(() => {
    backtestApi.watchlists().then(setNamedWatchlists).catch(() => {
      /* Watchlist filter just stays empty/unavailable — not fatal to the rest of the page. */
    })
  }, [])

  const distinctSymbols = useMemo(
    () => Array.from(new Set(results.map((r) => r.symbols))).sort(),
    [results],
  )
  const distinctTimeframes = useMemo(
    () => Array.from(new Set(results.map((r) => r.timeframe))).sort(),
    [results],
  )
  const distinctStoploss = useMemo(
    () => Array.from(new Set(results.map((r) => r.stoploss_pct))).sort((a, b) => a - b),
    [results],
  )
  const distinctTrailing = useMemo(
    () => Array.from(new Set(results.map((r) => r.trailing_pct))).sort((a, b) => a - b),
    [results],
  )

  const selectedWatchlist = namedWatchlists.find((w) => w.name === watchlistFilter) ?? null

  const filteredResults = useMemo(() => {
    const minTrades = minTradesFilter === "" ? null : Number(minTradesFilter)
    const filtered = results.filter(
      (r) =>
        (symbolsFilter === ALL_OPTION || r.symbols === symbolsFilter) &&
        (timeframeFilter === ALL_OPTION || r.timeframe === timeframeFilter) &&
        (slFilter === ALL_OPTION || String(r.stoploss_pct) === slFilter) &&
        (trailFilter === ALL_OPTION || String(r.trailing_pct) === trailFilter) &&
        (!selectedWatchlist || selectedWatchlist.symbols.includes(r.symbols)) &&
        (minTrades === null || r.total_trades >= minTrades),
    )
    if (sortMetric === NO_SORT) return filtered

    if (sortMetric === COMPOSITE_SCORE_KEY) {
      const scores = computeCompositeScores(filtered)
      return [...filtered].sort((a, b) => {
        const av = scores.get(a.id) ?? null
        const bv = scores.get(b.id) ?? null
        if (av === null) return bv === null ? 0 : 1
        if (bv === null) return -1
        return bv - av // higher composite score first
      })
    }

    const metric = SORT_METRICS.find((m) => m.key === sortMetric)
    if (!metric) return filtered

    return [...filtered].sort((a, b) => {
      const av = a[metric.key] as number | null
      const bv = b[metric.key] as number | null
      if (av === null) return bv === null ? 0 : 1 // missing metrics sort last regardless of direction
      if (bv === null) return -1
      return metric.direction === "desc" ? bv - av : av - bv
    })
  }, [results, symbolsFilter, timeframeFilter, slFilter, trailFilter, selectedWatchlist, minTradesFilter, sortMetric])

  // Only meaningful when sorted by composite score — recomputed from the
  // already-filtered set so labels reflect the same normalization the sort
  // itself used, not a stale/separate pass.
  const compositeScores = useMemo(
    () => (sortMetric === COMPOSITE_SCORE_KEY ? computeCompositeScores(filteredResults) : null),
    [sortMetric, filteredResults],
  )

  // A "recompute the combined view" action only makes sense when the
  // watchlist filter has narrowed the list down to rows that are all the
  // SAME tested combination, just split across different symbols — not an
  // arbitrary mix of timeframes/risk settings that a combined run couldn't
  // represent as one equity curve anyway.
  const sharedCombo = useMemo(() => {
    if (!selectedWatchlist || filteredResults.length === 0) return null
    const comboKey = (r: BacktestResultSummary) =>
      [
        r.timeframe, r.stoploss_pct, r.target_pct, r.trailing_pct, r.quantity,
        r.max_cycles_per_day, r.start_time, r.end_time, r.charges_enabled,
        r.date_from, r.date_to, r.strategy_params_json,
      ].join("|")
    const key = comboKey(filteredResults[0])
    return filteredResults.every((r) => comboKey(r) === key) ? filteredResults[0] : null
  }, [selectedWatchlist, filteredResults])

  // Any change to what's being viewed invalidates a previously recomputed
  // combined view — stale numbers under a new filter selection would be
  // actively misleading, worse than just clearing it.
  useEffect(() => {
    setCombinedView(null)
    setCombinedViewError(null)
  }, [watchlistFilter, sharedCombo])

  // A previously selected Top-N is computed from a specific snapshot of
  // filteredResults — invalidate it whenever that snapshot changes so a
  // stale selection never sits under a new set of filters, or gets
  // mistaken for having refreshed itself.
  useEffect(() => {
    setTopCandidates(null)
    setTopCandidatesConsidered(0)
    setExportTopError(null)
  }, [filteredResults])

  function handleSelectTopCandidates() {
    const n = Number(targetCount)
    const { candidates, consideredCount } = selectTopCandidates(
      filteredResults,
      Number.isFinite(n) && n > 0 ? n : DEFAULT_TARGET_COUNT,
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
      downloadBlob(blob, `${strategy}_top_${topCandidates.length}_candidates.xlsx`)
    } catch (e) {
      setExportTopError(e instanceof Error ? e.message : "Failed to export.")
    } finally {
      setExportingTop(false)
    }
  }

  async function handleRecomputeCombined() {
    if (!selectedWatchlist || !sharedCombo) return
    setCombinedViewLoading(true)
    setCombinedViewError(null)
    setCombinedView(null)
    try {
      const detail = await backtestApi.resultDetail(sharedCombo.id)
      const result = await backtestApi.run({
        strategy,
        symbols: selectedWatchlist.symbols,
        timeframe: sharedCombo.timeframe as CandleTimeframe,
        quantity: sharedCombo.quantity,
        stoploss_pct: sharedCombo.stoploss_pct,
        target_pct: sharedCombo.target_pct,
        trailing_pct: sharedCombo.trailing_pct,
        max_cycles_per_day: sharedCombo.max_cycles_per_day,
        start_time: sharedCombo.start_time,
        end_time: sharedCombo.end_time,
        capital: detail.result.capital,
        charges: sharedCombo.charges_enabled,
        date_from: sharedCombo.date_from,
        date_to: sharedCombo.date_to,
      })
      setCombinedView(result)
    } catch (e) {
      setCombinedViewError(e instanceof Error ? e.message : "Failed to recompute the combined view.")
    } finally {
      setCombinedViewLoading(false)
    }
  }

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
    setSymbolsFilter(ALL_OPTION)
    setTimeframeFilter(ALL_OPTION)
    setSlFilter(ALL_OPTION)
    setTrailFilter(ALL_OPTION)
    setWatchlistFilter(ALL_OPTION)
    setSortMetric(NO_SORT)
    setMinTradesFilter(String(DEFAULT_MIN_TRADES))
    setTargetCount(String(DEFAULT_TARGET_COUNT))
    setCombinedView(null)
    setCombinedViewError(null)
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

  async function handleCopyResearchBlob() {
    if (!detail) return
    const text = JSON.stringify(buildResearchBlob(detail), null, 2)
    setCopyError(null)
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopyError("Couldn't copy — your browser blocked clipboard access.")
    }
  }

  function downloadBlob(blob: Blob, filename: string) {
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  async function handleExportExcel() {
    setExporting(true)
    setExportError(null)
    try {
      const blob = await backtestApi.exportResultsExcel(strategy)
      downloadBlob(blob, `${strategy}_backtest_comparison.xlsx`)
    } catch (e) {
      setExportError(e instanceof Error ? e.message : "Failed to export.")
    } finally {
      setExporting(false)
    }
  }

  async function handleExportFiltered() {
    setExportingFiltered(true)
    setExportFilteredError(null)
    try {
      const blob = await backtestApi.exportSelectedResultsExcel(filteredResults.map((r) => r.id))
      downloadBlob(blob, `${strategy}_filtered_backtest_comparison.xlsx`)
    } catch (e) {
      setExportFilteredError(e instanceof Error ? e.message : "Failed to export.")
    } finally {
      setExportingFiltered(false)
    }
  }

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
              <option value={ALL_OPTION}>
                All ({filteredResults.length}
                {filteredResults.length !== results.length ? ` of ${results.length}` : ""}) — compare
              </option>
              {filteredResults.map((r) => (
                <option key={r.id} value={r.id}>
                  {comboLabel(r, compositeScores?.get(r.id))}
                </option>
              ))}
            </select>
          </label>
        </div>

        {results.length > 0 && (
          <div className="mt-4 grid grid-cols-2 gap-3 border-t border-[var(--glass-border)] pt-4 sm:grid-cols-3 lg:grid-cols-7">
            <label>
              <span className={labelClass}>Watchlist</span>
              <select
                className={fieldClass}
                value={watchlistFilter}
                onChange={(e) => setWatchlistFilter(e.target.value)}
                disabled={namedWatchlists.length === 0}
              >
                <option value={ALL_OPTION}>All</option>
                {namedWatchlists.map((w) => (
                  <option key={w.id} value={w.name}>
                    {w.name} ({w.symbols.length})
                  </option>
                ))}
              </select>
            </label>

            <label>
              <span className={labelClass}>Symbols</span>
              <select
                className={fieldClass}
                value={symbolsFilter}
                onChange={(e) => setSymbolsFilter(e.target.value)}
              >
                <option value={ALL_OPTION}>All</option>
                {distinctSymbols.map((s) => (
                  <option key={s} value={s} title={s}>
                    {symbolsLabel(s).length > 40 ? `${symbolsLabel(s).slice(0, 40)}…` : symbolsLabel(s)}
                  </option>
                ))}
              </select>
            </label>

            <label>
              <span className={labelClass}>Timeframe</span>
              <select
                className={fieldClass}
                value={timeframeFilter}
                onChange={(e) => setTimeframeFilter(e.target.value)}
              >
                <option value={ALL_OPTION}>All</option>
                {distinctTimeframes.map((tf) => (
                  <option key={tf} value={tf}>
                    {tf}
                  </option>
                ))}
              </select>
            </label>

            <label>
              <span className={labelClass}>Stop Loss %</span>
              <select className={fieldClass} value={slFilter} onChange={(e) => setSlFilter(e.target.value)}>
                <option value={ALL_OPTION}>All</option>
                {distinctStoploss.map((sl) => (
                  <option key={sl} value={sl}>
                    {sl}%
                  </option>
                ))}
              </select>
            </label>

            <label>
              <span className={labelClass}>Trailing %</span>
              <select
                className={fieldClass}
                value={trailFilter}
                onChange={(e) => setTrailFilter(e.target.value)}
              >
                <option value={ALL_OPTION}>All</option>
                {distinctTrailing.map((t) => (
                  <option key={t} value={t}>
                    {t}%
                  </option>
                ))}
              </select>
            </label>

            <label>
              <span className={labelClass}>Min Trades</span>
              <input
                type="number"
                min={0}
                className={fieldClass}
                value={minTradesFilter}
                onChange={(e) => setMinTradesFilter(e.target.value)}
                placeholder="No minimum"
                title="Hide combos with too few trades to trust their metrics — a 3-trade combo can post a huge profit factor by pure luck"
              />
            </label>

            <label>
              <span className={labelClass}>Sort By Metric</span>
              <select
                className={fieldClass}
                value={sortMetric}
                onChange={(e) => setSortMetric(e.target.value)}
              >
                <option value={NO_SORT}>None (as tested)</option>
                <option
                  value={COMPOSITE_SCORE_KEY}
                  title="Profit Factor 30% + Sharpe Ratio 25% + Expectancy 25% + Max Drawdown % 20% (inverted, lower is better) into one 0-1 score, normalized across the currently filtered combos. Win Rate and Total P&L are deliberately excluded — see lib/topCandidateSelection.ts"
                >
                  Composite Score (recommended)
                </option>
                {SORT_METRICS.map((m) => (
                  <option key={m.key} value={m.key}>
                    {m.label} ({m.direction === "desc" ? "best first" : "lowest first"})
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}

        {results.length > 0 && (
          <div className="mt-4 flex flex-wrap items-end justify-between gap-3 border-t border-[var(--glass-border)] pt-4">
            <p className="max-w-xl text-xs text-[var(--ink-muted)]">
              Picks ~N combinations worth deeper research from the {filteredResults.length} currently filtered
              combination{filteredResults.length === 1 ? "" : "s"} — not just the top Profit Factor, but a
              diverse set of quality, statistically credible, parameter-stable regions. See the Selection Reason
              column for why each one was picked.
            </p>
            <div className="flex items-end gap-2">
              <label>
                <span className={labelClass}>Target Count</span>
                <input
                  type="number"
                  min={1}
                  className={fieldClass}
                  value={targetCount}
                  onChange={(e) => setTargetCount(e.target.value)}
                  style={{ width: "6rem" }}
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

      {selectedWatchlist && (
        <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] p-5 backdrop-blur-sm">
          {sharedCombo ? (
            <>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-sm text-[var(--ink-secondary)]">
                  {filteredResults.length} per-symbol result{filteredResults.length === 1 ? "" : "s"} match this
                  exact combination across <strong>{selectedWatchlist.name}</strong>. Recompute the combined
                  view (one equity curve, one Sharpe/drawdown across all of them together) — this re-runs the
                  backtest live, a stored per-symbol result can't be validly combined after the fact.
                </p>
                <button
                  type="button"
                  onClick={handleRecomputeCombined}
                  disabled={combinedViewLoading}
                  className="shrink-0 rounded-md bg-[var(--accent)] px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                >
                  {combinedViewLoading ? "Recomputing…" : "Recompute Combined View"}
                </button>
              </div>
              {combinedViewError && (
                <p className="mt-2 text-xs text-[var(--status-critical)]">{combinedViewError}</p>
              )}
            </>
          ) : (
            <p className="text-sm text-[var(--ink-muted)]">
              <strong>{selectedWatchlist.name}</strong>'s matching results span more than one tested
              combination — narrow down with the other filters (Timeframe, Stop Loss %, Trailing %, ...)
              until they're all the same combination to recompute a combined view for them.
            </p>
          )}

          {combinedView && (
            <div className="mt-5 flex flex-col gap-5 border-t border-[var(--glass-border)] pt-5">
              <SummaryCardRow metrics={combinedView.metrics} />
              <ChartCard
                title="Equity Curve"
                subtitle={`Cumulative P&L across every closed trade, all ${selectedWatchlist.symbols.length} symbols in ${selectedWatchlist.name} combined`}
              >
                <EquityCurveChart points={combinedView.equity_curve} />
              </ChartCard>
            </div>
          )}
        </div>
      )}

      {loading && <p className="text-sm text-[var(--ink-muted)]">Loading…</p>}

      {!loading && selection === ALL_OPTION && (
        <ChartCard
          title="Parameter Comparison"
          subtitle={
            filteredResults.length === results.length
              ? "Every stored run for this strategy — click a bar (or pick it above) to see its full breakdown"
              : `${filteredResults.length} of ${results.length} stored runs match the filters above — click a bar (or pick it above) to see its full breakdown`
          }
          action={
            <div className="flex flex-col items-end gap-1">
              <button
                type="button"
                onClick={handleExportExcel}
                disabled={exporting || results.length === 0}
                title="Download every stored run for this strategy (not just the filtered view) as one .xlsx — handy for a spreadsheet or pasting/uploading into an LLM"
                className="shrink-0 rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5 text-xs font-medium hover:bg-[var(--page)] disabled:opacity-50"
              >
                {exporting ? "Exporting…" : "Export Excel"}
              </button>
              {exportError && <p className="text-[11px] text-[var(--status-critical)]">{exportError}</p>}
              <button
                type="button"
                onClick={handleExportFiltered}
                disabled={exportingFiltered || filteredResults.length === 0}
                title="Download only the runs matching the filters above (Watchlist/Symbols/Timeframe/Stop Loss %/Trailing %) as one .xlsx"
                className="shrink-0 rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5 text-xs font-medium hover:bg-[var(--page)] disabled:opacity-50"
              >
                {exportingFiltered
                  ? "Exporting…"
                  : `Export Filtered (${filteredResults.length})`}
              </button>
              {exportFilteredError && (
                <p className="text-[11px] text-[var(--status-critical)]">{exportFilteredError}</p>
              )}
            </div>
          }
        >
          <BacktestComparisonChart
            results={filteredResults}
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
                  View full JSON (conditions + run parameters + metrics)
                </summary>
                <div className="mt-2 flex items-center justify-between gap-3">
                  <span className="text-xs text-[var(--ink-muted)]">
                    Everything about this run in one block — paste it wherever you're researching tuning ideas.
                  </span>
                  <button
                    type="button"
                    onClick={handleCopyResearchBlob}
                    className="shrink-0 rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1 text-xs hover:bg-[var(--page)]"
                  >
                    {copied ? "Copied!" : "Copy"}
                  </button>
                </div>
                {copyError && <p className="mt-1 text-xs text-[var(--status-critical)]">{copyError}</p>}
                <pre className="mt-2 max-h-96 overflow-auto rounded-md bg-[var(--surface-2)] p-3 text-xs">
                  {JSON.stringify(buildResearchBlob(detail), null, 2)}
                </pre>
              </details>
            </div>
          )}

          <SummaryCardRow metrics={detail.result.metrics} />

          <MetricsGlossary />

          <ChartCard title="Equity Curve" subtitle="Cumulative P&L across every closed trade in this run">
            <EquityCurveChart points={detail.result.equity_curve ?? []} />
          </ChartCard>

          {/* by_symbol/by_market_condition are empty (not absent) for a
              sweep-saved result — run_backtest.py --sweep only has
              aggregated metrics per config, not the raw trades a
              breakdown needs — but default defensively anyway in case
              anything up the chain ever produces a genuinely missing
              field instead of an empty array. */}
          <StrategyTable
            rows={detail.result.by_symbol ?? []}
            title="By Symbol"
            firstColumnLabel="Symbol"
            searchPlaceholder="Search symbols…"
          />
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
