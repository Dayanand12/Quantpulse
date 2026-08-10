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
  // Full plain-language explanation, shown on hover — what the number
  // means AND what counts as good vs bad, not just a formula. Written for
  // someone who isn't already familiar with trading metrics.
  tooltip: string
  // Short always-visible words next to the trend arrow (not hover-only —
  // easy to miss a tooltip) — goodLabel when trend is "up", badLabel when
  // trend is "down". Omitted for cards with no trend() (e.g. Total
  // Trades, where more/fewer isn't inherently good or bad).
  goodLabel?: string
  badLabel?: string
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
    tooltip:
      "How many trades this run closed. Not good or bad by itself — but more trades means the other numbers on this page are statistically more trustworthy. A great Profit Factor from only 3 trades could easily be luck; the same number from 300 trades means a lot more.",
    icon: IconTrades,
    accent: "--card-blue",
    value: (m) => m.total_trades,
    format: (n) => n.toLocaleString("en-IN"),
  },
  {
    key: "win_rate",
    label: "Win Rate",
    tooltip:
      "The share of trades that closed profitable. Higher is generally better — but don't judge a strategy on this alone: a high win rate made of small wins and rare huge losses can still lose money overall. Always check Profit Factor and Net P&L alongside it.",
    goodLabel: "Good",
    badLabel: "Below 50%",
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
    tooltip:
      "Total money won ÷ total money lost. Above 1.0 means the strategy made more than it lost overall. Below 1.0 means it's a NET LOSER even if some individual trades won — this is one of the clearest good/bad signals here. Rough guide: below 1.0 is bad, 1.0–1.3 is marginal, 1.5+ is solid.",
    goodLabel: "Profitable",
    badLabel: "Losing money",
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
    tooltip:
      "Actual rupees made or lost, after brokerage and taxes — the real bottom line. Positive (green) is good, negative (red) is bad. Unlike Win Rate or Profit Factor, this already accounts for HOW BIG each win/loss was, so it's the single most direct answer to \"did this make money.\"",
    goodLabel: "Profitable",
    badLabel: "Net loss",
    icon: IconTrendingUp,
    accent: "--card-orange",
    value: (m) => m.total_pnl,
    format: (n) => fmtCurrency(n),
    trend: (m) => (m.total_pnl >= 0 ? "up" : "down"),
  },
  {
    key: "max_drawdown",
    label: "Max Drawdown",
    tooltip:
      "The worst losing streak in this run — the biggest drop from a peak before it recovered. Lower is better: a large drawdown means bigger swings and more risk of running out of capital (or losing confidence and abandoning the strategy) before it recovers. Shown here as a rupee amount below 5% of capital reads as healthy.",
    goodLabel: "Manageable",
    badLabel: "Large swing",
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
    tooltip:
      "Return per unit of RISK taken, not just raw profit — it rewards steady, consistent gains and penalizes wild swings, even between two strategies with similar total profit. Higher is better: below 1 is weak, 1–2 is decent, above 2 is very good. Needs at least 2 trading days of data to compute at all.",
    goodLabel: "Good",
    badLabel: "Weak",
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
            className="flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium"
            style={{
              color: trend === "up" ? "var(--status-good)" : "var(--status-critical)",
              background: `color-mix(in srgb, var(${trend === "up" ? "--status-good" : "--status-critical"}) 14%, transparent)`,
            }}
          >
            <span aria-hidden>{trend === "up" ? "▲" : "▼"}</span>
            {(trend === "up" ? config.goodLabel : config.badLabel) ??
              (trend === "up" ? "Good" : "Weak")}
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
