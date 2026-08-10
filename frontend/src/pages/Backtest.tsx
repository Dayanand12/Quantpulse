import { ChartCard } from "../components/analytics/ChartCard"
import { EquityCurveChart } from "../components/analytics/EquityCurveChart"
import { StrategyTable } from "../components/analytics/StrategyTable"
import { SummaryCardRow } from "../components/analytics/SummaryCard"
import { BacktestForm } from "../components/backtest/BacktestForm"
import { BacktestTradesTable } from "../components/backtest/BacktestTradesTable"
import { BatchRunner } from "../components/backtest/BatchRunner"
import { BulkUpload } from "../components/backtest/BulkUpload"
import { backtestApi } from "../lib/backtestApi"
import type { BacktestRunConfig } from "../lib/backtestTypes"
import { playBacktestCompleteSound } from "../lib/notifySound"
import { useBacktestPageStore } from "../store/backtestPageStore"

export function Backtest() {
  const config = useBacktestPageStore((s) => s.config)
  const result = useBacktestPageStore((s) => s.result)
  const running = useBacktestPageStore((s) => s.running)
  const error = useBacktestPageStore((s) => s.error)
  const setConfig = useBacktestPageStore((s) => s.setConfig)
  const setResult = useBacktestPageStore((s) => s.setResult)
  const setRunning = useBacktestPageStore((s) => s.setRunning)
  const setError = useBacktestPageStore((s) => s.setError)

  async function runBacktest(resolvedConfig: BacktestRunConfig) {
    setRunning(true)
    setError(null)
    try {
      const res = await backtestApi.run(resolvedConfig)
      setResult(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Backtest failed.")
    } finally {
      setRunning(false)
      playBacktestCompleteSound()
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Backtest</h1>
        <p className="mt-1 text-sm text-[var(--ink-muted)]">
          Pick a strategy, choose symbols, run it against historical data, and see exactly which
          stocks and market conditions it did (or didn't) work in.
        </p>
      </div>

      <BacktestForm config={config} onChange={setConfig} onRun={runBacktest} running={running} />

      {config.strategy && <BatchRunner strategy={config.strategy} sharedConfig={config} />}

      {config.strategy && <BulkUpload strategy={config.strategy} sharedConfig={config} />}

      {error && (
        <p className="rounded-lg border border-[var(--status-critical)]/40 bg-[var(--status-critical)]/10 px-4 py-3 text-sm text-[var(--status-critical)]">
          {error}
        </p>
      )}

      {running && !result && (
        <p className="text-sm text-[var(--ink-muted)]">
          Running — a full watchlist backtest over 22 months can take 20-30 seconds.
        </p>
      )}

      {result && (
        <div className={`flex flex-col gap-6 transition-opacity duration-300 ${running ? "opacity-60" : "opacity-100"}`}>
          <div className="rounded-lg border border-[var(--glass-border)] bg-[var(--glass-surface)] px-4 py-3 text-sm text-[var(--ink-secondary)]">
            Ran on {result.symbols_used.length} symbol(s): {result.symbols_used.join(", ")}
            {result.symbols_missing_data.length > 0 && (
              <span className="ml-2 text-[var(--status-critical)]">
                (no historical data for: {result.symbols_missing_data.join(", ")})
              </span>
            )}
          </div>

          <SummaryCardRow metrics={result.metrics} />

          <ChartCard title="Equity Curve" subtitle="Cumulative P&L across every closed trade in this run">
            <EquityCurveChart points={result.equity_curve} />
          </ChartCard>

          <StrategyTable
            rows={result.by_symbol}
            title="By Symbol — which stocks this worked on"
            firstColumnLabel="Symbol"
            searchPlaceholder="Search symbols…"
          />

          <StrategyTable
            rows={result.by_market_condition}
            title="By Market Condition — which conditions this worked in"
            firstColumnLabel="Condition"
            searchPlaceholder="Search conditions…"
          />

          <StrategyTable
            rows={result.by_side}
            title="By Side"
            firstColumnLabel="Side"
            searchPlaceholder="Search…"
          />

          <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] p-5 backdrop-blur-sm">
            <h3 className="mb-4 text-sm font-semibold text-[var(--ink-primary)]">Trade Log</h3>
            <BacktestTradesTable trades={result.trades} truncated={result.trades_truncated} />
          </div>
        </div>
      )}
    </div>
  )
}
