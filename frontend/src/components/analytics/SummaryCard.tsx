import type { ComponentType, SVGProps } from "react"
import { fmtCurrency, fmtNumber, fmtPercent } from "../../lib/format"
import type { PerformanceMetrics } from "../../lib/types"
import { AnimatedNumber } from "./AnimatedNumber"
import {
  IconActivity,
  IconPercent,
  IconTarget,
  IconTrades,
  IconTrendingDown,
  IconTrendingUp,
} from "./icons"

type Trend = "up" | "down" | null

export interface MetricCardConfig {
  key: string
  label: string
  tooltip: string
  icon: ComponentType<SVGProps<SVGSVGElement>>
  accent: string // CSS var name, e.g. "--card-blue"
  value: (m: PerformanceMetrics) => number | null
  format: (n: number) => string
  na?: string
  trend?: (m: PerformanceMetrics) => Trend
}

// Single declarative source for every summary card. Adding a future
// metric (Sortino, Calmar, Expectancy, ...) once it exists on
// PerformanceMetrics is one entry here — no new component, no JSX to
// touch in the page.
export const METRIC_CARDS: MetricCardConfig[] = [
  {
    key: "total_trades",
    label: "Total Trades",
    tooltip: "Every closed trade matching the current filters",
    icon: IconTrades,
    accent: "--card-blue",
    value: (m) => m.total_trades,
    format: (n) => n.toLocaleString("en-IN"),
  },
  {
    key: "win_rate",
    label: "Win Rate",
    tooltip: "Winning trades / total trades",
    icon: IconTarget,
    accent: "--card-green",
    value: (m) => m.win_rate,
    format: (n) => fmtPercent(n),
    na: "no trades yet",
    trend: (m) => (m.win_rate === null ? null : m.win_rate >= 50 ? "up" : "down"),
  },
  {
    key: "profit_factor",
    label: "Profit Factor",
    tooltip: "Gross profit / |gross loss| — above 1.0 means the strategy is net profitable",
    icon: IconPercent,
    accent: "--card-purple",
    value: (m) => m.profit_factor,
    format: (n) => fmtNumber(n),
    na: "no losing trades yet",
    trend: (m) => (m.profit_factor === null ? null : m.profit_factor >= 1 ? "up" : "down"),
  },
  {
    key: "total_pnl",
    label: "Net P&L",
    tooltip: "Total realized profit and loss across every matching trade",
    icon: IconTrendingUp,
    accent: "--card-orange",
    value: (m) => m.total_pnl,
    format: (n) => fmtCurrency(n),
    trend: (m) => (m.total_pnl >= 0 ? "up" : "down"),
  },
  {
    key: "max_drawdown",
    label: "Max Drawdown",
    tooltip: "Largest peak-to-trough drop in cumulative P&L",
    icon: IconTrendingDown,
    accent: "--card-teal",
    value: (m) => m.max_drawdown,
    format: (n) => fmtCurrency(n),
    // Below 5% of capital reads as healthy; purely a display cue, not a
    // risk threshold anyone should rely on.
    trend: (m) =>
      m.max_drawdown_pct === null ? null : m.max_drawdown_pct < 5 ? "up" : "down",
  },
  {
    key: "sharpe_ratio",
    label: "Sharpe Ratio",
    tooltip: "Annualized, daily-bucketed risk-adjusted return",
    icon: IconActivity,
    accent: "--card-red",
    value: (m) => m.sharpe_ratio,
    format: (n) => fmtNumber(n),
    na: "need 2+ trading days",
    trend: (m) => (m.sharpe_ratio === null ? null : m.sharpe_ratio >= 1 ? "up" : "down"),
  },
]

function SummaryCard({ config, metrics }: { config: MetricCardConfig; metrics: PerformanceMetrics }) {
  const raw = config.value(metrics)
  const trend = config.trend?.(metrics) ?? null
  const Icon = config.icon

  return (
    <div
      title={config.tooltip}
      className="group relative overflow-hidden rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] p-5 backdrop-blur-sm transition-all duration-300 hover:-translate-y-0.5 hover:border-white/20 hover:shadow-lg hover:shadow-black/20"
    >
      <div
        aria-hidden
        className="pointer-events-none absolute -right-6 -top-6 h-24 w-24 rounded-full opacity-10 blur-2xl transition-opacity duration-300 group-hover:opacity-20"
        style={{ background: `var(${config.accent})` }}
      />

      <div className="relative flex items-start justify-between">
        <div
          className="flex h-9 w-9 items-center justify-center rounded-xl"
          style={{
            background: `color-mix(in srgb, var(${config.accent}) 18%, transparent)`,
            color: `var(${config.accent})`,
          }}
        >
          <Icon />
        </div>

        {trend && (
          <span
            aria-label={trend === "up" ? "trending favorably" : "trending unfavorably"}
            className="tabular-nums text-xs font-medium"
            style={{ color: trend === "up" ? "var(--status-good)" : "var(--status-critical)" }}
          >
            {trend === "up" ? "▲" : "▼"}
          </span>
        )}
      </div>

      <div className="relative mt-4 text-sm text-[var(--ink-muted)]">{config.label}</div>
      <div className="relative mt-1 text-2xl font-semibold text-[var(--ink-primary)]">
        {raw === null ? (
          <span className="text-sm font-normal text-[var(--ink-muted)]">
            N/A{config.na ? ` — ${config.na}` : ""}
          </span>
        ) : (
          <AnimatedNumber value={raw} format={config.format} />
        )}
      </div>
    </div>
  )
}

export function SummaryCardRow({ metrics }: { metrics: PerformanceMetrics }) {
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-6">
      {METRIC_CARDS.map((config) => (
        <SummaryCard key={config.key} config={config} metrics={metrics} />
      ))}
    </div>
  )
}
