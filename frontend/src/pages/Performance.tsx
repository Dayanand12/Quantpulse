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

const PERIOD_LABEL = { daily: "Daily", weekly: "Weekly", monthly: "Monthly" } as const

export function Performance() {
  const { filters, setFilters, resetFilters, data, loading, error } = useAnalytics()
  const showSkeleton = loading && !data

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

          <StrategyTable rows={data.by_strategy} />

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
