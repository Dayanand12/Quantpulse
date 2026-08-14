// Selecting ~100 combinations worth deeper research out of a 16,000+ row
// sweep is NOT "sort by Profit Factor, take the top 100" — that rewards
// small-sample luck and hands back 100 near-identical variations of
// whichever single parameter region got lucky. This module does it in the
// three stages actually discussed with the user:
//
//   1. Quality filter (caller's job, via a min-trades threshold) + a
//      Composite Score blending four normalized metrics.
//   2. A Stability Score — is this candidate's score representative of the
//      parameter neighborhood around it, or an isolated spike?
//   3. Greedy diversity selection — don't let near-duplicate parameter
//      combos crowd out distinct regions.
//
// Everything here is pure (no React, no fetch) and operates only on
// BacktestResultSummary fields that already exist on the API response —
// see CLAUDE.md's per-symbol result-storage note for why "symbol" is part
// of a row's identity, not something to aggregate away here.
import type { BacktestResultSummary } from "./backtestTypes"

// ---------------------------------------------------------------------------
// Shared numeric helpers
// ---------------------------------------------------------------------------

function clamp01(v: number): number {
  return Math.max(0, Math.min(1, v))
}

export function safeNumber(v: number | null | undefined): number | null {
  if (v === null || v === undefined || !Number.isFinite(v)) return null
  return v
}

// Expectancy isn't a stored field — it's the average net P&L per trade,
// derived from total_pnl/total_trades (both already on the summary). This
// is distinct from raw total_pnl (which the user explicitly asked to
// exclude from the score): dividing by trade count removes the bias
// toward "whichever combo happened to fire the most signals" that raw
// total_pnl carries.
export function computeExpectancy(r: BacktestResultSummary): number | null {
  if (r.total_trades <= 0) return null
  const pnl = safeNumber(r.total_pnl)
  return pnl === null ? null : pnl / r.total_trades
}

// Min-max normalizes within whatever set is passed in (the current
// eligible/filtered rows), not some fixed universal scale — "a good
// Sharpe ratio" only means something relative to what this strategy/
// symbol/date-range combination can actually produce.
//
// Edge cases handled: nulls pass through as null (excluded, not zeroed);
// non-finite values (NaN/Infinity) are treated the same as null; an
// all-identical set (max === min) normalizes every real value to a
// neutral 0.5 rather than inflating everyone to 1 — a metric that can't
// differentiate anything shouldn't manufacture a false "this is the best"
// signal (a uniform shift like this also can't change relative order
// within the tied group either way).
export function normalize(values: (number | null)[]): (number | null)[] {
  const nums = values.filter((v): v is number => v !== null && Number.isFinite(v))
  if (nums.length === 0) return values.map(() => null)
  const min = Math.min(...nums)
  const max = Math.max(...nums)
  if (max === min) {
    return values.map((v) => (v !== null && Number.isFinite(v) ? 0.5 : null))
  }
  return values.map((v) => (v !== null && Number.isFinite(v) ? (v - min) / (max - min) : null))
}

// ---------------------------------------------------------------------------
// Stage 1 — Composite Score
// ---------------------------------------------------------------------------

interface CompositeMetricSpec {
  key: string
  label: string
  weight: number
  invert: boolean // true = lower raw value is better (e.g. drawdown)
  extract: (r: BacktestResultSummary) => number | null
  // Profit Factor, Sharpe and Max Drawdown % are already scale-invariant
  // (ratios/percentages) — comparable across different symbols directly.
  // Expectancy is raw currency (total_pnl/total_trades) and is NOT: a
  // ~₹11,000 stock (e.g. MARUTI) racks up a far bigger rupee P&L per trade
  // than a ~₹200 stock for an equivalent quality of edge, purely from
  // share price, since quantity is fixed rather than capital-normalized.
  // Confirmed against the real 16k-row dataset: without this, MARUTI rows
  // filled 9 of the top 10 slots on Expectancy's absolute scale alone.
  // Normalizing within each row's own group (same symbol/timeframe/date
  // range/charges — the same grouping Stage 2/3 already use) fixes this
  // without needing an entry-price field this API doesn't expose.
  normalizeWithinGroup?: boolean
}

// Weights as agreed: Profit Factor 30%, Sharpe 25%, Expectancy 25%,
// Max Drawdown % 20% (inverted). Win Rate is deliberately excluded from
// the score (kept as a visible diagnostic column only) and Total P&L is
// excluded entirely (see computeExpectancy's comment). Tune by editing
// this array — weights are re-normalized over whatever's actually
// available per-row, so they don't need to be re-balanced by hand if a
// metric is added/removed.
export const COMPOSITE_METRICS: CompositeMetricSpec[] = [
  { key: "profit_factor", label: "Profit Factor", weight: 0.3, invert: false, extract: (r) => safeNumber(r.profit_factor) },
  { key: "sharpe_ratio", label: "Sharpe Ratio", weight: 0.25, invert: false, extract: (r) => safeNumber(r.sharpe_ratio) },
  { key: "expectancy", label: "Expectancy", weight: 0.25, invert: false, extract: (r) => computeExpectancy(r), normalizeWithinGroup: true },
  { key: "max_drawdown_pct", label: "Max Drawdown %", weight: 0.2, invert: true, extract: (r) => safeNumber(r.max_drawdown_pct) },
]

// A row missing one metric (e.g. sharpe_ratio null — fewer than 2 trading
// days) is re-weighted over just the metrics it does have, so Composite
// Score itself stays a fair 0..1 reading of "how good is this on the
// evidence available." A row missing ALL four gets `null` (can't be
// scored at all — excluded upstream by the caller). Missing data isn't
// ignored beyond that, though — see computeMetricCompleteness below,
// which the Final Score uses to discount a partial-evidence row so it
// can't outrank a fully-measured one purely by omission (confirmed
// against the real 16k-row dataset: a row with only 2 of 4 metrics
// available was topping the raw composite ranking before this discount
// was added).
const TOTAL_COMPOSITE_WEIGHT = COMPOSITE_METRICS.reduce((s, m) => s + m.weight, 0)

export function computeMetricCompleteness(r: BacktestResultSummary): number {
  const availableWeight = COMPOSITE_METRICS.reduce((s, m) => s + (m.extract(r) === null ? 0 : m.weight), 0)
  return availableWeight / TOTAL_COMPOSITE_WEIGHT
}

export function missingMetricLabels(r: BacktestResultSummary): string[] {
  return COMPOSITE_METRICS.filter((m) => m.extract(r) === null).map((m) => m.label)
}

export function computeCompositeScores(rows: BacktestResultSummary[]): Map<number, number | null> {
  const byGroup = groupRowsByKey(rows)

  // One normalized value per row per metric, keyed by row id — global
  // metrics normalize across all of `rows`; normalizeWithinGroup metrics
  // (currently just Expectancy) normalize separately inside each group so
  // a higher-priced symbol's naturally larger rupee numbers don't get
  // compared against a lower-priced symbol's.
  const normalizedByMetric = new Map<string, Map<number, number | null>>()
  for (const metric of COMPOSITE_METRICS) {
    const perRow = new Map<number, number | null>()
    const rawOf = (r: BacktestResultSummary) => {
      const raw = metric.extract(r)
      return raw === null ? null : (metric.invert ? -raw : raw)
    }
    if (metric.normalizeWithinGroup) {
      for (const groupRows of byGroup.values()) {
        const norm = normalize(groupRows.map(rawOf))
        groupRows.forEach((r, i) => perRow.set(r.id, norm[i]))
      }
    } else {
      const norm = normalize(rows.map(rawOf))
      rows.forEach((r, i) => perRow.set(r.id, norm[i]))
    }
    normalizedByMetric.set(metric.key, perRow)
  }

  const scores = new Map<number, number | null>()
  for (const r of rows) {
    const parts = COMPOSITE_METRICS.map((m) => ({
      v: normalizedByMetric.get(m.key)!.get(r.id) ?? null,
      weight: m.weight,
    })).filter((p): p is { v: number; weight: number } => p.v !== null)

    if (parts.length === 0) {
      scores.set(r.id, null)
      continue
    }
    const totalWeight = parts.reduce((s, p) => s + p.weight, 0)
    scores.set(r.id, parts.reduce((s, p) => s + p.v * p.weight, 0) / totalWeight)
  }
  return scores
}

// ---------------------------------------------------------------------------
// Parameter vector + grouping — the actual tunable structure in this app
// ---------------------------------------------------------------------------
//
// There is no "ORB window" parameter in this codebase (the opening range
// is fixed at 9:15-9:30) — the real per-row tunable axes are the flat risk
// fields plus whatever's in strategy_params_json's `parameters` block
// (e.g. adx_min/adx_max/volume_ratio_min for the ORB strategies, different
// keys for other strategies). This builds a generic {name: number} vector
// from both so neighbor/similarity logic works for any strategy without a
// backend change.

const RISK_PARAM_KEYS = ["stoploss_pct", "target_pct", "trailing_pct", "quantity", "max_cycles_per_day"] as const

function parseIndicatorParams(rawJson: string): Record<string, number> {
  if (!rawJson) return {}
  try {
    const parsed = JSON.parse(rawJson) as { parameters?: Record<string, unknown> }
    const params = parsed.parameters ?? {}
    const out: Record<string, number> = {}
    for (const [k, v] of Object.entries(params)) {
      if (typeof v === "number" && Number.isFinite(v)) out[k] = v
    }
    return out
  } catch {
    return {}
  }
}

export function extractParamVector(r: BacktestResultSummary): Record<string, number> {
  const vector: Record<string, number> = {}
  for (const key of RISK_PARAM_KEYS) {
    const v = r[key]
    if (typeof v === "number" && Number.isFinite(v)) vector[key] = v
  }
  Object.assign(vector, parseIndicatorParams(r.strategy_params_json))
  return vector
}

// Two rows are only comparable as "nearby parameter combinations" if
// they're the same symbol, timeframe, date range and charges setting —
// comparing SL=0.8 on RELIANCE against SL=0.8 on INFY isn't a parameter
// neighbor relationship, it's a different research question entirely.
export function groupKey(r: BacktestResultSummary): string {
  return [r.strategy_name, r.symbols, r.timeframe, r.date_from, r.date_to, r.charges_enabled, r.start_time, r.end_time].join("||")
}

function groupRowsByKey(rows: BacktestResultSummary[]): Map<string, BacktestResultSummary[]> {
  const groups = new Map<string, BacktestResultSummary[]>()
  for (const r of rows) {
    const key = groupKey(r)
    const arr = groups.get(key)
    if (arr) arr.push(r)
    else groups.set(key, [r])
  }
  return groups
}

interface GroupInfo {
  rows: BacktestResultSummary[]
  vectors: Map<number, Record<string, number>>
  dims: string[]
  // Sorted distinct values actually present in this group, per dimension —
  // "do NOT require every neighboring combination to exist" falls out
  // naturally: we only ever look at values that are actually in this list.
  distinctByDim: Map<string, number[]>
}

function buildGroups(rows: BacktestResultSummary[]): Map<string, GroupInfo> {
  const groups = new Map<string, GroupInfo>()
  for (const [key, groupRows] of groupRowsByKey(rows)) {
    const vectors = new Map(groupRows.map((r) => [r.id, extractParamVector(r)] as const))
    groups.set(key, { rows: groupRows, vectors, dims: [], distinctByDim: new Map() })
  }
  for (const g of groups.values()) {
    const dimSet = new Set<string>()
    for (const v of g.vectors.values()) for (const k of Object.keys(v)) dimSet.add(k)
    g.dims = Array.from(dimSet)
    for (const d of g.dims) {
      const vals = Array.from(new Set(g.rows.map((r) => g.vectors.get(r.id)![d]).filter((v) => v !== undefined)))
      vals.sort((a, b) => a - b)
      g.distinctByDim.set(d, vals)
    }
  }
  return groups
}

// ---------------------------------------------------------------------------
// Stage 2 — Stability Score
// ---------------------------------------------------------------------------
//
// For each candidate, an "axis neighbor" is another row in the same group
// (same symbol/timeframe/date range/charges) that's identical on every
// OTHER dimension and one adjacent step away on exactly one dimension
// (adjacent = next value in that dimension's own sorted, distinct,
// actually-tested value list — e.g. SL 0.8's neighbors are whatever SL
// values were actually tested immediately above/below 0.8 in this group,
// with target/trailing/quantity/adx_min/... all held fixed).
//
// Stability = how close the neighbors' Composite Scores are to this
// candidate's own score (1 - |gap|, averaged, clamped to [0,1]). A flat
// local plateau of similarly-strong scores scores high; a candidate whose
// neighbors score very differently (a spike OR a cliff) scores low —
// exactly the "isolated performance spike" the user wants demoted. No
// neighbors tested nearby at all -> stability 0 (no evidence either way,
// treated the same as "not confirmed stable" rather than rewarded for
// being untested).
//
// Complexity is O(groupSize^2 * dims) per group — fine at the group sizes
// this app currently produces (one symbol's own parameter sweep, a few
// hundred rows at most); if a future sweep pushes a single group into the
// tens of thousands of rows, bucket by "signature of all other dims" first
// instead of the current full pairwise scan.
function computeStabilityScores(
  groups: Map<string, GroupInfo>,
  compositeScores: Map<number, number | null>,
): Map<number, { stability: number; neighborCount: number }> {
  const result = new Map<number, { stability: number; neighborCount: number }>()

  for (const group of groups.values()) {
    for (const r of group.rows) {
      const vecA = group.vectors.get(r.id)!
      const neighborIds = new Set<number>()

      for (const d of group.dims) {
        const distinct = group.distinctByDim.get(d)!
        const idxA = distinct.indexOf(vecA[d])
        if (idxA === -1) continue
        const adjacent = new Set([distinct[idxA - 1], distinct[idxA + 1]].filter((v) => v !== undefined))
        if (adjacent.size === 0) continue

        for (const other of group.rows) {
          if (other.id === r.id) continue
          const vecB = group.vectors.get(other.id)!
          const sameOnOtherDims = group.dims.every((dd) => dd === d || vecB[dd] === vecA[dd])
          if (sameOnOtherDims && adjacent.has(vecB[d])) neighborIds.add(other.id)
        }
      }

      if (neighborIds.size === 0) {
        result.set(r.id, { stability: 0, neighborCount: 0 })
        continue
      }

      const scoreA = compositeScores.get(r.id) ?? null
      if (scoreA === null) {
        result.set(r.id, { stability: 0, neighborCount: neighborIds.size })
        continue
      }

      let sum = 0
      let counted = 0
      for (const nid of neighborIds) {
        const scoreN = compositeScores.get(nid)
        if (scoreN === undefined || scoreN === null) continue
        sum += clamp01(1 - Math.abs(scoreA - scoreN))
        counted++
      }
      result.set(r.id, { stability: counted > 0 ? sum / counted : 0, neighborCount: neighborIds.size })
    }
  }

  return result
}

// ---------------------------------------------------------------------------
// Trade-count evidence
// ---------------------------------------------------------------------------
//
// A statistical-confidence factor, separate from the min-trades cutoff the
// caller already applies: a 300-trade combo is more trustworthy than a
// 51-trade one even though both cleared the same floor. Scaled by sqrt(n)
// (standard error of an estimate shrinks with sqrt(n), not n) and
// saturating at the reference point so the marginal benefit of going from
// 50->100 trades matters more than 500->550.
//
// 300 is tuned for equity's multi-year, single-symbol backtests. A single
// option CONTRACT lives a few weeks (confirmed against real data: pages/
// OptionsAnalysis.tsx's own min-trades default had to drop from 50 to 5
// for the same reason — a strategy topped out at 7 trades per contract
// across 983 stored results), so 300 would flatten every option result
// into the bottom of the confidence curve and barely differentiate a
// well-sampled 80-trade contract from a 5-trade fluke. Callers comparing
// option results should pass OPTIONS_TRADE_CONFIDENCE_REFERENCE instead —
// equity callers keep the default, unaffected.
const TRADE_CONFIDENCE_REFERENCE = 300
export const OPTIONS_TRADE_CONFIDENCE_REFERENCE = 50

export function computeTradeConfidence(totalTrades: number, reference: number = TRADE_CONFIDENCE_REFERENCE): number {
  if (totalTrades <= 0) return 0
  return clamp01(Math.sqrt(totalTrades) / Math.sqrt(reference))
}

// ---------------------------------------------------------------------------
// Stage 3 — Diversity / redundancy control
// ---------------------------------------------------------------------------
//
// Normalized Euclidean distance over the parameter vector, each dimension
// scaled by that GROUP's own min/max range (a dimension that's constant
// within the group contributes nothing — it has no differentiating power
// there). Rows in different groups (different symbol/timeframe/date range)
// are never compared for similarity — they're inherently distinct research
// questions, not redundant with each other.
const DIVERSITY_SIMILARITY_THRESHOLD = 0.12

function paramDistance(vecA: Record<string, number>, vecB: Record<string, number>, group: GroupInfo): number {
  let sumSq = 0
  let counted = 0
  for (const d of group.dims) {
    const distinct = group.distinctByDim.get(d)!
    if (distinct.length <= 1) continue
    const min = distinct[0]
    const max = distinct[distinct.length - 1]
    const a = vecA[d]
    const b = vecB[d]
    if (a === undefined || b === undefined) continue
    const norm = (a - b) / (max - min)
    sumSq += norm * norm
    counted++
  }
  if (counted === 0) return 0
  return Math.sqrt(sumSq / counted)
}

// ---------------------------------------------------------------------------
// Final ranking
// ---------------------------------------------------------------------------

export interface ScoredCandidate {
  result: BacktestResultSummary
  expectancy: number | null
  compositeScore: number | null
  metricCompleteness: number
  stabilityScore: number
  neighborCount: number
  tradeConfidence: number
  finalScore: number | null
  rank: number
  selectionReason: string
}

interface PreliminaryCandidate {
  result: BacktestResultSummary
  expectancy: number | null
  compositeScore: number | null
  metricCompleteness: number
  stabilityScore: number
  neighborCount: number
  tradeConfidence: number
  finalScore: number | null
}

// Final Score = Composite Score damped by stability, trade-count
// confidence, and metric completeness, rather than added to them — these
// three are a CONFIDENCE DISCOUNT on quality, not independent axes a
// mediocre-but-robust combo could use to outrank a genuinely better one.
// Each factor has a 0.5 floor: even a totally isolated/low-evidence/
// partial-data candidate keeps half its composite score (real trade data
// already established some quality in Stage 1), it's just not privileged
// over a confirmed-robust, fully-measured candidate with the same raw
// composite score. Always <= compositeScore.
function computeFinalScore(
  compositeScore: number | null,
  stability: number,
  tradeConfidence: number,
  metricCompleteness: number,
): number | null {
  if (compositeScore === null) return null
  const stabilityFactor = 0.5 + 0.5 * stability
  const tradeFactor = 0.5 + 0.5 * tradeConfidence
  const completenessFactor = 0.5 + 0.5 * metricCompleteness
  return compositeScore * stabilityFactor * tradeFactor * completenessFactor
}

function greedyDiverseSelect(
  candidates: PreliminaryCandidate[],
  targetCount: number,
  groups: Map<string, GroupInfo>,
): { candidate: PreliminaryCandidate; wasRedundant: boolean }[] {
  const selected: { candidate: PreliminaryCandidate; wasRedundant: boolean }[] = []
  const leftovers: PreliminaryCandidate[] = []

  for (const c of candidates) {
    if (selected.length >= targetCount) break
    const key = groupKey(c.result)
    const group = groups.get(key)!
    const cVec = group.vectors.get(c.result.id)!
    const tooSimilar = selected.some((s) => {
      if (groupKey(s.candidate.result) !== key) return false
      return paramDistance(cVec, group.vectors.get(s.candidate.result.id)!, group) < DIVERSITY_SIMILARITY_THRESHOLD
    })
    if (tooSimilar) {
      leftovers.push(c)
    } else {
      selected.push({ candidate: c, wasRedundant: false })
    }
  }

  // Backfill from skipped near-duplicates (already in descending
  // finalScore order) if diversity filtering couldn't fill the target —
  // better to return the requested count, appropriately demoted to the
  // bottom of the list, than to under-deliver.
  for (const c of leftovers) {
    if (selected.length >= targetCount) break
    selected.push({ candidate: c, wasRedundant: true })
  }

  return selected
}

function qualitativeLabel(score: number | null): "high" | "moderate" | "low" | "unavailable" {
  if (score === null) return "unavailable"
  if (score >= 0.66) return "high"
  if (score >= 0.33) return "moderate"
  return "low"
}

function buildSelectionReason(c: PreliminaryCandidate, wasRedundant: boolean): string {
  const compositeLabel = qualitativeLabel(c.compositeScore)
  const missing = missingMetricLabels(c.result)
  const compositeText =
    compositeLabel === "unavailable"
      ? "insufficient metrics for a composite score"
      : `${compositeLabel} composite score` + (missing.length > 0 ? ` (based on partial data — missing ${missing.join(", ")})` : "")

  const stabilityText =
    c.neighborCount === 0
      ? "no neighboring parameter combinations tested nearby (isolated result)"
      : `${qualitativeLabel(c.stabilityScore)} parameter stability across ${c.neighborCount} nearby combination${c.neighborCount === 1 ? "" : "s"}`

  const tradeText = `${c.result.total_trades} trades`

  const diversityText = wasRedundant
    ? "kept to reach the target count despite being similar to a higher-ranked candidate"
    : "not redundant with a higher-ranked candidate"

  const parts = [compositeText, stabilityText, tradeText, diversityText]
  return parts[0].charAt(0).toUpperCase() + parts[0].slice(1) + ", " + parts.slice(1).join(", ") + "."
}

export const DEFAULT_MIN_TRADES = 50
export const DEFAULT_TARGET_COUNT = 100

// Shared "sort a filtered result list" logic for pages/Analysis.tsx and
// pages/OptionsAnalysis.tsx — same metric choices, same composite-score
// tie-breaking (missing metrics always sort last regardless of direction,
// since a null win_rate isn't "worse," it's "unknown").
export const COMPOSITE_SCORE_SORT_KEY = "__composite__"
export const NO_SORT_KEY = "__none__"

export const SORT_METRICS: { key: keyof BacktestResultSummary; label: string; direction: "asc" | "desc" }[] = [
  { key: "win_rate", label: "Win Rate", direction: "desc" },
  { key: "profit_factor", label: "Profit Factor", direction: "desc" },
  { key: "total_pnl", label: "Total P&L", direction: "desc" },
  { key: "sharpe_ratio", label: "Sharpe Ratio", direction: "desc" },
  { key: "max_drawdown_pct", label: "Max Drawdown %", direction: "asc" },
  { key: "total_trades", label: "Total Trades", direction: "desc" },
]

export function sortResultSummaries(
  results: BacktestResultSummary[],
  sortMetric: string,
  compositeScores?: Map<number, number | null>,
): BacktestResultSummary[] {
  if (sortMetric === NO_SORT_KEY) return results

  if (sortMetric === COMPOSITE_SCORE_SORT_KEY) {
    const scores = compositeScores ?? computeCompositeScores(results)
    return [...results].sort((a, b) => {
      const av = scores.get(a.id) ?? null
      const bv = scores.get(b.id) ?? null
      if (av === null) return bv === null ? 0 : 1
      if (bv === null) return -1
      return bv - av
    })
  }

  const metric = SORT_METRICS.find((m) => m.key === sortMetric)
  if (!metric) return results
  return [...results].sort((a, b) => {
    const av = a[metric.key] as number | null
    const bv = b[metric.key] as number | null
    if (av === null) return bv === null ? 0 : 1
    if (bv === null) return -1
    return metric.direction === "desc" ? bv - av : av - bv
  })
}

// Rows saved before this session's per-symbol result-storage refactor (or
// via run_backtest.py --sweep, which only ever saves aggregated metrics)
// carry symbols="WATCHLIST" or a literal comma-joined symbol list instead
// of one symbol — a whole-portfolio result, not "a parameter combination
// for a symbol". Mixing these into the Top-N selection is comparing
// apples to oranges (confirmed against the real dataset: a handful of
// these, with trade counts in the thousands, otherwise crowd out single-
// symbol candidates entirely via the trade-confidence factor). Excluded
// here only — the rest of the Analysis tab (filters, chart, exports)
// still shows them exactly as before.
export function isSingleSymbolRow(r: BacktestResultSummary): boolean {
  return r.symbols !== "WATCHLIST" && !r.symbols.includes(",")
}

export interface TopCandidateSelection {
  candidates: ScoredCandidate[]
  consideredCount: number // single-symbol rows actually fed into scoring, after the WATCHLIST/multi-symbol exclusion above
}

// Entry point. `eligibleRows` should already be quality-filtered by the
// caller (e.g. Analysis.tsx's Min Trades filter) — this module doesn't
// re-apply a trade-count floor itself, it only uses trade count as a
// continuous confidence factor (computeTradeConfidence) on top of whatever
// floor the caller chose. `tradeConfidenceReference` defaults to equity's
// scale (see OPTIONS_TRADE_CONFIDENCE_REFERENCE above) — pages/
// OptionsAnalysis.tsx passes the options one instead.
export function selectTopCandidates(
  eligibleRows: BacktestResultSummary[],
  targetCount: number,
  tradeConfidenceReference: number = TRADE_CONFIDENCE_REFERENCE,
): TopCandidateSelection {
  const rows = eligibleRows.filter(isSingleSymbolRow)
  if (rows.length === 0 || targetCount <= 0) return { candidates: [], consideredCount: rows.length }

  const groups = buildGroups(rows)
  const compositeScores = computeCompositeScores(rows)
  const stability = computeStabilityScores(groups, compositeScores)

  const preliminary: PreliminaryCandidate[] = rows
    .map((r) => {
      const compositeScore = compositeScores.get(r.id) ?? null
      const stab = stability.get(r.id) ?? { stability: 0, neighborCount: 0 }
      const tradeConfidence = computeTradeConfidence(r.total_trades, tradeConfidenceReference)
      const metricCompleteness = computeMetricCompleteness(r)
      return {
        result: r,
        expectancy: computeExpectancy(r),
        compositeScore,
        metricCompleteness,
        stabilityScore: stab.stability,
        neighborCount: stab.neighborCount,
        tradeConfidence,
        finalScore: computeFinalScore(compositeScore, stab.stability, tradeConfidence, metricCompleteness),
      }
    })
    .filter((c) => c.compositeScore !== null) // nothing usable to rank a row with zero available metrics on
    .sort((a, b) => (b.finalScore ?? -Infinity) - (a.finalScore ?? -Infinity))

  const selected = greedyDiverseSelect(preliminary, targetCount, groups)

  return {
    candidates: selected.map(({ candidate, wasRedundant }, i) => ({
      ...candidate,
      rank: i + 1,
      selectionReason: buildSelectionReason(candidate, wasRedundant),
    })),
    consideredCount: rows.length,
  }
}
