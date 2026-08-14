import { useMemo, useState } from "react"
import { fmtNumber, fmtPercent } from "../../lib/format"
import { formatStrategyParams } from "../../lib/backtestTypes"
import type { ScoredCandidate } from "../../lib/topCandidateSelection"
import { EmptyState } from "./EmptyState"
import { IconSearch } from "./icons"

function scoreColor(v: number | null): string {
  if (v === null) return "var(--ink-muted)"
  if (v >= 0.66) return "var(--status-good)"
  if (v >= 0.33) return "var(--ink-secondary)"
  return "var(--status-critical)"
}

interface TopCandidatesTableProps {
  candidates: ScoredCandidate[]
  consideredCount: number
  onExport: () => void
  exporting: boolean
  exportError: string | null
}

export function TopCandidatesTable({
  candidates,
  consideredCount,
  onExport,
  exporting,
  exportError,
}: TopCandidatesTableProps) {
  const [search, setSearch] = useState("")

  const filtered = useMemo(() => {
    if (!search.trim()) return candidates
    const q = search.toLowerCase()
    return candidates.filter(
      (c) => c.result.symbols.toLowerCase().includes(q) || String(c.result.id).includes(q),
    )
  }, [candidates, search])

  return (
    <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] p-5 backdrop-blur-sm">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-[var(--ink-primary)]">
            Top {candidates.length} Candidates for Deeper Research
          </h3>
          <p className="mt-0.5 text-xs text-[var(--ink-muted)]">
            Selected from {consideredCount} eligible combination{consideredCount === 1 ? "" : "s"} — ranked by
            Final Score (Composite Score damped by parameter stability and trade-count confidence), with
            near-duplicate parameter regions filtered for diversity.
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <div className="flex items-center gap-2">
            <div className="relative">
              <IconSearch className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--ink-muted)]" />
              <input
                type="text"
                placeholder="Search symbol or ID…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="rounded-xl border border-[var(--glass-border)] bg-[var(--surface-2)] py-2 pl-9 pr-3 text-sm text-[var(--ink-primary)] outline-none transition-colors focus:border-[var(--accent)]"
              />
            </div>
            <button
              type="button"
              onClick={onExport}
              disabled={exporting || candidates.length === 0}
              title="Export this selection to Excel — same file format as the other exports on this page"
              className="shrink-0 rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5 text-xs font-medium hover:bg-[var(--page)] disabled:opacity-50"
            >
              {exporting ? "Exporting…" : "Export Selection"}
            </button>
          </div>
          {exportError && <p className="text-[11px] text-[var(--status-critical)]">{exportError}</p>}
        </div>
      </div>

      {candidates.length === 0 ? (
        <EmptyState title="No candidates selected yet" subtitle="Click “Select Top N” above to run the selection." />
      ) : (
        <div className="max-h-[600px] overflow-auto rounded-xl">
          <table className="w-full border-collapse text-sm">
            <thead className="sticky top-0 z-10 bg-[var(--surface-2)]">
              <tr>
                {[
                  "Rank", "ID", "Symbol", "Timeframe", "Parameters", "Trades",
                  "Profit Factor", "Sharpe", "Expectancy", "Max DD %", "Win Rate",
                  "Composite", "Stability", "Final Score", "Selection Reason",
                ].map((label) => (
                  <th
                    key={label}
                    className="whitespace-nowrap px-3 py-2.5 text-left text-xs font-medium text-[var(--ink-muted)]"
                  >
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((c, i) => (
                <tr
                  key={c.result.id}
                  className={`transition-colors hover:bg-white/[0.04] ${i % 2 === 1 ? "bg-white/[0.015]" : ""}`}
                >
                  <td className="whitespace-nowrap border-t border-[var(--glass-border)] px-3 py-2.5 font-semibold tabular-nums">
                    {c.rank}
                  </td>
                  <td className="whitespace-nowrap border-t border-[var(--glass-border)] px-3 py-2.5 tabular-nums text-[var(--ink-muted)]">
                    {c.result.id}
                  </td>
                  <td className="whitespace-nowrap border-t border-[var(--glass-border)] px-3 py-2.5 font-medium text-[var(--ink-primary)]">
                    {c.result.symbols}
                  </td>
                  <td className="whitespace-nowrap border-t border-[var(--glass-border)] px-3 py-2.5">
                    {c.result.timeframe}
                  </td>
                  <td className="whitespace-nowrap border-t border-[var(--glass-border)] px-3 py-2.5 text-xs text-[var(--ink-secondary)]">
                    {`SL ${c.result.stoploss_pct}/TP ${c.result.target_pct}/Trail ${c.result.trailing_pct}`}
                    {formatStrategyParams(c.result.strategy_params_json) &&
                      ` · ${formatStrategyParams(c.result.strategy_params_json)}`}
                  </td>
                  <td className="whitespace-nowrap border-t border-[var(--glass-border)] px-3 py-2.5 text-right tabular-nums">
                    {c.result.total_trades}
                  </td>
                  <td className="whitespace-nowrap border-t border-[var(--glass-border)] px-3 py-2.5 text-right tabular-nums">
                    {fmtNumber(c.result.profit_factor)}
                  </td>
                  <td className="whitespace-nowrap border-t border-[var(--glass-border)] px-3 py-2.5 text-right tabular-nums">
                    {fmtNumber(c.result.sharpe_ratio)}
                  </td>
                  <td className="whitespace-nowrap border-t border-[var(--glass-border)] px-3 py-2.5 text-right tabular-nums">
                    {fmtNumber(c.expectancy)}
                  </td>
                  <td className="whitespace-nowrap border-t border-[var(--glass-border)] px-3 py-2.5 text-right tabular-nums">
                    {fmtPercent(c.result.max_drawdown_pct)}
                  </td>
                  <td className="whitespace-nowrap border-t border-[var(--glass-border)] px-3 py-2.5 text-right tabular-nums">
                    {fmtPercent(c.result.win_rate)}
                  </td>
                  <td
                    className="whitespace-nowrap border-t border-[var(--glass-border)] px-3 py-2.5 text-right font-semibold tabular-nums"
                    style={{ color: scoreColor(c.compositeScore) }}
                  >
                    {c.compositeScore === null ? "—" : c.compositeScore.toFixed(2)}
                  </td>
                  <td
                    className="whitespace-nowrap border-t border-[var(--glass-border)] px-3 py-2.5 text-right tabular-nums"
                    style={{ color: scoreColor(c.stabilityScore) }}
                  >
                    {c.stabilityScore.toFixed(2)}
                    <span className="ml-1 text-[10px] text-[var(--ink-muted)]">({c.neighborCount}n)</span>
                  </td>
                  <td
                    className="whitespace-nowrap border-t border-[var(--glass-border)] px-3 py-2.5 text-right font-semibold tabular-nums"
                    style={{ color: scoreColor(c.finalScore) }}
                  >
                    {c.finalScore === null ? "—" : c.finalScore.toFixed(2)}
                  </td>
                  <td className="max-w-[320px] border-t border-[var(--glass-border)] px-3 py-2.5 text-xs text-[var(--ink-secondary)]">
                    {c.selectionReason}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
