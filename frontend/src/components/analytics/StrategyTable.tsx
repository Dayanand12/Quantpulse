import type { ReactNode } from "react"
import { useMemo, useState } from "react"
import { fmtCurrency, fmtNumber, fmtPercent } from "../../lib/format"
import type { StrategyBreakdown } from "../../lib/types"
import { EmptyState } from "./EmptyState"
import { IconSearch } from "./icons"

interface ColumnConfig {
  key: string
  label: string
  align: "left" | "right"
  value: (row: StrategyBreakdown) => number | string | null
  render?: (row: StrategyBreakdown) => ReactNode
}

function pnlColor(v: number): string {
  return v >= 0 ? "var(--status-good)" : "var(--status-critical)"
}

// Single declarative source for every column — adding a future metric
// (Sortino, Calmar, ...) is one entry here, not new table markup.
const TABLE_COLUMNS: ColumnConfig[] = [
  { key: "strategy_name", label: "Strategy", align: "left", value: (r) => r.strategy_name },
  {
    key: "timeframe",
    label: "Timeframe",
    align: "left",
    value: (r) => r.timeframe,
    render: (r) => r.timeframe ?? "—",
  },
  { key: "total_trades", label: "Trades", align: "right", value: (r) => r.metrics.total_trades },
  {
    key: "win_rate",
    label: "Win Rate",
    align: "right",
    value: (r) => r.metrics.win_rate,
    render: (r) => (r.metrics.win_rate === null ? "—" : fmtPercent(r.metrics.win_rate)),
  },
  {
    key: "gross_profit",
    label: "Gross Profit",
    align: "right",
    value: (r) => r.metrics.gross_profit,
    render: (r) => (
      <span style={{ color: pnlColor(r.metrics.gross_profit) }}>
        {fmtCurrency(r.metrics.gross_profit)}
      </span>
    ),
  },
  {
    key: "gross_loss",
    label: "Gross Loss",
    align: "right",
    value: (r) => r.metrics.gross_loss,
    render: (r) => (
      <span style={{ color: pnlColor(r.metrics.gross_loss) }}>
        {fmtCurrency(r.metrics.gross_loss)}
      </span>
    ),
  },
  {
    key: "total_pnl",
    label: "Net P&L",
    align: "right",
    value: (r) => r.metrics.total_pnl,
    render: (r) => (
      <span className="font-semibold" style={{ color: pnlColor(r.metrics.total_pnl) }}>
        {fmtCurrency(r.metrics.total_pnl)}
      </span>
    ),
  },
  {
    key: "profit_factor",
    label: "Profit Factor",
    align: "right",
    value: (r) => r.metrics.profit_factor,
    render: (r) => (r.metrics.profit_factor === null ? "—" : fmtNumber(r.metrics.profit_factor)),
  },
  {
    key: "avg_r_multiple",
    label: "Avg R",
    align: "right",
    value: (r) => r.metrics.avg_r_multiple,
    render: (r) =>
      r.metrics.avg_r_multiple === null ? "—" : `${fmtNumber(r.metrics.avg_r_multiple)}R`,
  },
  {
    key: "sharpe_ratio",
    label: "Sharpe",
    align: "right",
    value: (r) => r.metrics.sharpe_ratio,
    render: (r) => (r.metrics.sharpe_ratio === null ? "—" : fmtNumber(r.metrics.sharpe_ratio)),
  },
  {
    key: "max_drawdown",
    label: "Max DD",
    align: "right",
    value: (r) => r.metrics.max_drawdown,
    render: (r) => fmtCurrency(r.metrics.max_drawdown),
  },
  {
    key: "max_drawdown_pct",
    label: "Max DD %",
    align: "right",
    value: (r) => r.metrics.max_drawdown_pct,
    render: (r) =>
      r.metrics.max_drawdown_pct === null ? "—" : fmtPercent(r.metrics.max_drawdown_pct),
  },
]

type SortDir = "asc" | "desc"

interface StrategyTableProps {
  rows: StrategyBreakdown[]
  title?: string
  firstColumnLabel?: string
  searchPlaceholder?: string
  // When set, rows become clickable — used by the Performance page to
  // drill from a strategy's aggregate metrics into its individual trades.
  onSelectRow?: (row: StrategyBreakdown) => void
  // Keyed by deployment_id, not strategy_name — the same strategy can be
  // deployed more than once (e.g. two timeframes), which would otherwise
  // highlight every row sharing that name instead of just the clicked one.
  selectedDeploymentId?: string | null
}

export function StrategyTable({
  rows,
  title = "Strategy Comparison",
  firstColumnLabel = "Strategy",
  searchPlaceholder = "Search strategies…",
  onSelectRow,
  selectedDeploymentId,
}: StrategyTableProps) {
  const [search, setSearch] = useState("")
  const [sortKey, setSortKey] = useState("total_pnl")
  const [sortDir, setSortDir] = useState<SortDir>("desc")

  const filtered = useMemo(
    () => rows.filter((r) => r.strategy_name.toLowerCase().includes(search.toLowerCase())),
    [rows, search],
  )

  const sorted = useMemo(() => {
    const col = TABLE_COLUMNS.find((c) => c.key === sortKey)
    if (!col) return filtered

    return [...filtered].sort((a, b) => {
      const av = col.value(a)
      const bv = col.value(b)
      if (av === null && bv === null) return 0
      if (av === null) return 1
      if (bv === null) return -1

      const cmp =
        typeof av === "string" || typeof bv === "string"
          ? String(av).localeCompare(String(bv))
          : av - bv

      return sortDir === "asc" ? cmp : -cmp
    })
  }, [filtered, sortKey, sortDir])

  function toggleSort(key: string) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"))
    } else {
      setSortKey(key)
      setSortDir("desc")
    }
  }

  return (
    <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] p-5 backdrop-blur-sm">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-[var(--ink-primary)]">{title}</h3>
        <div className="relative">
          <IconSearch className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--ink-muted)]" />
          <input
            type="text"
            placeholder={searchPlaceholder}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="rounded-xl border border-[var(--glass-border)] bg-[var(--surface-2)] py-2 pl-9 pr-3 text-sm text-[var(--ink-primary)] outline-none transition-colors focus:border-[var(--accent)]"
          />
        </div>
      </div>

      {rows.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="max-h-[420px] overflow-auto rounded-xl">
          <table className="w-full border-collapse text-sm">
            <thead className="sticky top-0 z-10 bg-[var(--surface-2)]">
              <tr>
                {TABLE_COLUMNS.map((col) => (
                  <th
                    key={col.key}
                    onClick={() => toggleSort(col.key)}
                    className={`cursor-pointer select-none whitespace-nowrap px-3 py-2.5 text-xs font-medium text-[var(--ink-muted)] transition-colors hover:text-[var(--ink-primary)] ${
                      col.align === "right" ? "text-right" : "text-left"
                    }`}
                  >
                    {col.key === "strategy_name" ? firstColumnLabel : col.label}
                    {sortKey === col.key && (
                      <span className="ml-1">{sortDir === "asc" ? "↑" : "↓"}</span>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.length === 0 ? (
                <tr>
                  <td colSpan={TABLE_COLUMNS.length} className="px-3 py-8">
                    <EmptyState
                      title="No strategies match your search"
                      subtitle="Try a different search term."
                    />
                  </td>
                </tr>
              ) : (
                sorted.map((row, i) => (
                  <tr
                    key={row.deployment_id ?? `${row.strategy_name}-${i}`}
                    onClick={onSelectRow ? () => onSelectRow(row) : undefined}
                    className={`transition-colors hover:bg-white/[0.04] ${
                      i % 2 === 1 ? "bg-white/[0.015]" : ""
                    } ${onSelectRow ? "cursor-pointer" : ""} ${
                      selectedDeploymentId != null && selectedDeploymentId === row.deployment_id
                        ? "bg-[var(--accent)]/10"
                        : ""
                    }`}
                  >
                    {TABLE_COLUMNS.map((col) => (
                      <td
                        key={col.key}
                        className={`tabular-nums whitespace-nowrap border-t border-[var(--glass-border)] px-3 py-2.5 ${
                          col.align === "right"
                            ? "text-right"
                            : "text-left font-medium text-[var(--ink-primary)]"
                        }`}
                      >
                        {col.render ? col.render(row) : String(col.value(row) ?? "—")}
                      </td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
