import { ChartCard } from "../components/analytics/ChartCard"
import { EquityCurveChart } from "../components/analytics/EquityCurveChart"
import { StrategyTable } from "../components/analytics/StrategyTable"
import { SummaryCardRow } from "../components/analytics/SummaryCard"
import { BacktestTradesTable } from "../components/backtest/BacktestTradesTable"
import { ChainSweepPanel } from "../components/backtest/ChainSweepPanel"
import { OptionsBacktestForm } from "../components/backtest/OptionsBacktestForm"
import { RollingAtmPanel } from "../components/backtest/RollingAtmPanel"
import { backtestApi } from "../lib/backtestApi"
import { playBacktestCompleteSound } from "../lib/notifySound"
import { useOptionsBacktestPageStore } from "../store/optionsBacktestPageStore"

// Mirrors pages/Backtest.tsx's results display exactly (SummaryCardRow/
// EquityCurveChart/StrategyTable/BacktestTradesTable all read the same
// generic result shape regardless of what was backtested) — the only real
// difference from the equity page is OptionsBacktestForm's contract
// picker in place of a watchlist/symbol picker, and a `warnings` banner
// for things like a quantity that isn't a whole multiple of the
// contract's real lot size (see core/domain/charges.py's options rate
// card and historical_loader.py::validate_lot_multiple on the backend).
export function OptionsBacktest() {
  const config = useOptionsBacktestPageStore((s) => s.config)
  const contractSymbol = useOptionsBacktestPageStore((s) => s.contractSymbol)
  const result = useOptionsBacktestPageStore((s) => s.result)
  const running = useOptionsBacktestPageStore((s) => s.running)
  const error = useOptionsBacktestPageStore((s) => s.error)
  const sweepId = useOptionsBacktestPageStore((s) => s.sweepId)
  const setConfig = useOptionsBacktestPageStore((s) => s.setConfig)
  const setContractSymbol = useOptionsBacktestPageStore((s) => s.setContractSymbol)
  const setResult = useOptionsBacktestPageStore((s) => s.setResult)
  const setRunning = useOptionsBacktestPageStore((s) => s.setRunning)
  const setError = useOptionsBacktestPageStore((s) => s.setError)
  const setSweepId = useOptionsBacktestPageStore((s) => s.setSweepId)

  async function runBacktest() {
    if (!contractSymbol) return
    setRunning(true)
    setError(null)
    try {
      const res = await backtestApi.run({ ...config, symbols: [contractSymbol] })
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
        <h1 className="text-2xl font-semibold">Options Backtest</h1>
        <p className="mt-1 text-sm text-[var(--ink-muted)]">
          Pick one option contract — underlying, expiry, strike, side — and run a strategy directly
          against its own premium history. Manual contract selection only; no automatic ATM/rolling
          logic yet.
        </p>
      </div>

      <OptionsBacktestForm
        config={config}
        contractSymbol={contractSymbol}
        onChangeConfig={setConfig}
        onChangeContract={setContractSymbol}
        onRun={runBacktest}
        running={running}
      />

      {config.strategy && <ChainSweepPanel config={config} sweepId={sweepId} onSweepIdChange={setSweepId} />}

      {config.strategy && <RollingAtmPanel config={config} />}

      {error && (
        <p className="rounded-lg border border-[var(--status-critical)]/40 bg-[var(--status-critical)]/10 px-4 py-3 text-sm text-[var(--status-critical)]">
          {error}
        </p>
      )}

      {running && !result && <p className="text-sm text-[var(--ink-muted)]">Running…</p>}

      {result && (
        <div className={`flex flex-col gap-6 transition-opacity duration-300 ${running ? "opacity-60" : "opacity-100"}`}>
          <div className="rounded-lg border border-[var(--glass-border)] bg-[var(--glass-surface)] px-4 py-3 text-sm text-[var(--ink-secondary)]">
            Ran on {result.symbols_used.join(", ") || "(nothing — check the contract has data)"}
            {result.symbols_missing_data.length > 0 && (
              <span className="ml-2 text-[var(--status-critical)]">
                (no historical data for: {result.symbols_missing_data.join(", ")})
              </span>
            )}
          </div>

          {(result.warnings ?? []).length > 0 && (
            <div className="rounded-lg border border-[var(--status-warning,#b45309)]/40 bg-[var(--status-warning,#b45309)]/10 px-4 py-3 text-sm text-[var(--status-warning,#b45309)]">
              {(result.warnings ?? []).map((w) => (
                <p key={w}>{w}</p>
              ))}
            </div>
          )}

          <SummaryCardRow metrics={result.metrics} />

          <ChartCard title="Equity Curve" subtitle="Cumulative P&L across every closed trade in this run">
            <EquityCurveChart points={result.equity_curve} />
          </ChartCard>

          <StrategyTable
            rows={result.by_market_condition}
            title="By Market Condition — which conditions this worked in"
            firstColumnLabel="Condition"
            searchPlaceholder="Search conditions…"
          />

          <StrategyTable rows={result.by_side} title="By Side" firstColumnLabel="Side" searchPlaceholder="Search…" />

          {result.by_oi_level.length > 0 && (
            <StrategyTable
              rows={result.by_oi_level}
              title="By OI Level — open interest at entry, split into thirds for this run"
              firstColumnLabel="OI Level"
              searchPlaceholder="Search…"
            />
          )}

          <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] p-5 backdrop-blur-sm">
            <h3 className="mb-4 text-sm font-semibold text-[var(--ink-primary)]">Trade Log</h3>
            <BacktestTradesTable trades={result.trades} truncated={result.trades_truncated} showOi />
          </div>
        </div>
      )}
    </div>
  )
}
