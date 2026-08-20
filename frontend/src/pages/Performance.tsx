import { useEffect, useState } from "react"
import { BacktestTradesTable } from "../components/backtest/BacktestTradesTable"
import { ChartCard } from "../components/analytics/ChartCard"
import { DrawdownChart } from "../components/analytics/DrawdownChart"
import { EquityCurveChart } from "../components/analytics/EquityCurveChart"
import { FilterBar } from "../components/analytics/FilterBar"
import { CardSkeleton, ChartSkeleton, TableSkeleton } from "../components/analytics/LoadingSkeleton"
import { MonthlyPnlChart } from "../components/analytics/MonthlyPnlChart"
import { ProfitHistogram } from "../components/analytics/ProfitHistogram"
import { RiskReturnScatter } from "../components/analytics/RiskReturnScatter"
import { RollingSharpeChart } from "../components/analytics/RollingSharpeChart"
import { StrategyComparisonBars } from "../components/analytics/StrategyComparisonBars"
import { StrategyCorrelationMatrix } from "../components/analytics/StrategyCorrelationMatrix"
import { StrategyHeatmap } from "../components/analytics/StrategyHeatmap"
import { StrategyTable } from "../components/analytics/StrategyTable"
import { StrategyTrendChart } from "../components/analytics/StrategyTrendChart"
import { SummaryCardRow } from "../components/analytics/SummaryCard"
import { WinRateGauge } from "../components/analytics/WinRateGauge"
import { useAnalytics } from "../hooks/useAnalytics"
import { api } from "../lib/api"
import type { StrategyBreakdown, Trade } from "../lib/types"

const PERIOD_LABEL = { daily: "Daily", weekly: "Weekly", monthly: "Monthly" } as const

export function Performance() {
  const { filters, setFilters, resetFilters, data, loading, error } = useAnalytics()
  const showSkeleton = loading && !data

  // Holds the whole row, not just strategy_name — the same strategy can be
  // deployed more than once (e.g. two timeframes), and only deployment_id
  // tells those apart when fetching this row's trades below.
  const [selectedRow, setSelectedRow] = useState<StrategyBreakdown | null>(null)
  const [strategyTrades, setStrategyTrades] = useState<Trade[]>([])
  const [tradesLoading, setTradesLoading] = useState(false)
  const [tradesError, setTradesError] = useState<string | null>(null)

  // Same filters already applied to the by_strategy breakdown above, so the
  // trades shown here always match the row's summarized metrics — narrowed
  // to just the clicked deployment (falling back to strategy_name alone
  // only for a deleted deployment, which has no deployment_id to filter on).
  useEffect(() => {
    if (!selectedRow) return
    let cancelled = false
    setTradesLoading(true)
    setTradesError(null)

    api
      .trades({
        strategy: selectedRow.strategy_name,
        deployment_id: selectedRow.deployment_id ?? undefined,
        symbol: filters.symbol,
        date_from: filters.date_from,
        date_to: filters.date_to,
      })
      .then((res) => {
        if (!cancelled) setStrategyTrades(res)
      })
      .catch(() => {
        if (!cancelled) setTradesError("Failed to load trades.")
      })
      .finally(() => {
        if (!cancelled) setTradesLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [selectedRow, filters.symbol, filters.date_from, filters.date_to])

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Performance</h1>
        <p className="mt-1 text-sm text-[var(--ink-muted)]">
          Every number below comes from the same metrics engine for every strategy — nothing
          here is strategy-specific.
        </p>
      </div>

      {error && <p className="text-sm text-[var(--status-critical)]">{error}</p>}

      <FilterBar
        filters={filters}
        setFilters={setFilters}
        onReset={resetFilters}
        availableStrategies={data?.available_strategies ?? []}
        availableSymbols={data?.available_symbols ?? []}
      />

      {showSkeleton && (
        <>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-6">
            {Array.from({ length: 6 }).map((_, i) => (
              <CardSkeleton key={i} />
            ))}
          </div>
          <TableSkeleton />
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <ChartSkeleton key={i} />
            ))}
          </div>
        </>
      )}

      {data && (
        <div
          className={`flex flex-col gap-6 transition-opacity duration-300 ${
            loading ? "opacity-60" : "opacity-100"
          }`}
        >
          <SummaryCardRow metrics={data.overall} />

          <StrategyTable
            rows={data.by_strategy}
            selectedDeploymentId={selectedRow?.deployment_id}
            onSelectRow={(row) =>
              setSelectedRow((prev) =>
                prev?.deployment_id === row.deployment_id && prev?.strategy_name === row.strategy_name
                  ? null
                  : row,
              )
            }
          />

          {selectedRow && (
            <ChartCard
              title={`${selectedRow.strategy_name}${selectedRow.timeframe ? ` (${selectedRow.timeframe})` : ""} — Trades`}
              subtitle="Every closed trade for this deployment under the current filters — check market condition at entry to see where it worked and where it didn't"
            >
              {tradesError && <p className="text-sm text-[var(--status-critical)]">{tradesError}</p>}
              {tradesLoading ? (
                <TableSkeleton />
              ) : (
                <BacktestTradesTable
                  trades={strategyTrades}
                  truncated={false}
                  showOi={strategyTrades.some((t) => t.entry_oi != null)}
                />
              )}
            </ChartCard>
          )}

          <ChartCard
            title="Strategy × Symbol"
            subtitle="Win rate by strategy and stock, under the current filters — add or remove a strategy and it appears/disappears here automatically"
          >
            <StrategyHeatmap
              rows={data.heatmap_strategy_symbol}
              columnLabel="Symbol"
              emptySubtitle="Needs closed trades with a strategy attached under the current filters."
            />
          </ChartCard>

          <ChartCard
            title="Strategy × Market Condition"
            subtitle="Win rate by strategy and entry-time market condition (Trending/Ranging × Volume × VWAP side) — narrow to one symbol above to drill in"
          >
            <StrategyHeatmap
              rows={data.heatmap_strategy_condition}
              columnLabel="Market Condition"
              emptySubtitle="Needs closed trades with a strategy and a recorded entry market condition."
            />
          </ChartCard>

          <ChartCard
            title="Strategy Trend"
            subtitle={`Cumulative P&L per strategy, ${PERIOD_LABEL[filters.timeframe].toLowerCase()} — is a strategy still working, or decaying?`}
          >
            <StrategyTrendChart points={data.strategy_trend} />
          </ChartCard>

          <ChartCard
            title="Strategy Correlation"
            subtitle="Pearson correlation of daily P&L between strategies — high correlation means they win/lose together, so running both adds less diversification than it looks like"
          >
            <StrategyCorrelationMatrix pairs={data.strategy_correlation} />
          </ChartCard>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <ChartCard title="Equity Curve" subtitle="Cumulative P&L across every closed trade">
              <EquityCurveChart points={data.equity_curve} />
            </ChartCard>

            <ChartCard title="Drawdown" subtitle="Running drawdown from the equity peak">
              <DrawdownChart points={data.drawdown} />
            </ChartCard>

            <ChartCard
              title={`${PERIOD_LABEL[filters.timeframe]} P&L`}
              subtitle="Net P&L per period, not cumulative"
            >
              <MonthlyPnlChart points={data.pnl_by_period} />
            </ChartCard>

            <ChartCard title="Rolling Sharpe" subtitle="Sharpe ratio over a trailing trading window">
              <RollingSharpeChart points={data.rolling_sharpe} />
            </ChartCard>

            <ChartCard title="Win Rate" subtitle="Share of trades closed profitably">
              <WinRateGauge value={data.overall.win_rate} />
            </ChartCard>

            <ChartCard title="Profit Distribution" subtitle="Histogram of per-trade P&L">
              <ProfitHistogram buckets={data.profit_distribution} />
            </ChartCard>

            <ChartCard
              title="Metrics by Strategy"
              subtitle="Win rate, profit factor, and Sharpe side by side"
            >
              <StrategyComparisonBars rows={data.by_strategy} />
            </ChartCard>

            <ChartCard title="Risk vs Return" subtitle="Drawdown % vs return % — size is |Sharpe|">
              <RiskReturnScatter rows={data.by_strategy} />
            </ChartCard>
          </div>
        </div>
      )}
    </div>
  )
}
