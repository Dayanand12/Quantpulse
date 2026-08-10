import { useEffect, useState } from "react"
import { fmtCurrency, fmtNumber, fmtPercent } from "../../lib/format"
import { useBatchRunnerStore } from "../../store/batchRunnerStore"
import type { BacktestRunConfig } from "../../lib/backtestTypes"

const fieldClass =
  "w-full rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5 text-sm outline-none focus:border-[var(--accent)]"
const textareaClass =
  "w-full rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 font-mono text-xs outline-none focus:border-[var(--accent)]"

interface BatchRunnerProps {
  strategy: string
  sharedConfig: BacktestRunConfig
}

// The "6 panels" feature: one strategy (fixed conditions.json structure),
// up to 6 different `parameters` value-sets tested against it in parallel
// — never overwrites strategies/<name>.json on disk (see
// runners/backtesting/batch_runner.py). Run state lives in
// store/batchRunnerStore.ts, not local component state — a batch run can
// take well over a minute, and this component unmounts every time you
// navigate to another page (React Router). The backend keeps running and
// saving results regardless of what the browser does; the store is what
// lets the UI still show them when you come back instead of looking reset.
export function BatchRunner({ strategy, sharedConfig }: BatchRunnerProps) {
  const [expanded, setExpanded] = useState(false)
  const panels = useBatchRunnerStore((s) => s.panels)
  const runningAll = useBatchRunnerStore((s) => s.runningAll)
  const globalError = useBatchRunnerStore((s) => s.globalError)
  const ensureSeededForStrategy = useBatchRunnerStore((s) => s.ensureSeededForStrategy)
  const updatePanel = useBatchRunnerStore((s) => s.updatePanel)
  const runIndices = useBatchRunnerStore((s) => s.runIndices)
  const runAll = useBatchRunnerStore((s) => s.runAll)

  useEffect(() => {
    ensureSeededForStrategy(strategy)
  }, [strategy, ensureSeededForStrategy])

  return (
    <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] p-5 backdrop-blur-sm">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center gap-1.5 text-sm font-semibold text-[var(--ink-primary)]"
      >
        <span>{expanded ? "▾" : "▸"}</span>
        Batch Parameter Tuning — up to 6 panels
        {panels.some((p) => p.running) && (
          <span className="ml-1 text-xs font-normal text-[var(--accent)]">running…</span>
        )}
      </button>

      {expanded && (
        <div className="mt-4">
          <p className="mb-4 text-xs text-[var(--ink-muted)]">
            One strategy (<strong>{strategy || "…"}</strong>), up to 6 different parameter value-sets,
            run in parallel against the same symbols/dates/risk settings configured above. Nothing here
            overwrites <code>strategies/{strategy || "…"}.json</code> — each panel's override is
            temporary, and a successful run still gets saved to the Analysis tab as its own comparable
            row. Runs keep going server-side even if you switch pages — come back and this panel still
            shows progress/results.
          </p>

          <div className="mb-4 flex items-center gap-3">
            <button
              type="button"
              onClick={() => runAll(strategy, sharedConfig)}
              disabled={runningAll || !strategy}
              className="rounded-md bg-[var(--accent)] px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              {runningAll ? "Running all…" : "Run All"}
            </button>
            {globalError && <p className="text-xs text-[var(--status-critical)]">{globalError}</p>}
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
            {panels.map((panel, i) => (
              <div key={i} className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-3">
                <input
                  type="text"
                  value={panel.label}
                  onChange={(e) => updatePanel(i, { label: e.target.value })}
                  className={`${fieldClass} mb-2 font-medium`}
                />
                <textarea
                  className={textareaClass}
                  rows={5}
                  spellCheck={false}
                  value={panel.overridesText}
                  onChange={(e) => updatePanel(i, { overridesText: e.target.value })}
                />
                <button
                  type="button"
                  onClick={() => runIndices(strategy, sharedConfig, [i])}
                  disabled={panel.running || runningAll || !strategy}
                  className="mt-2 rounded-md border border-[var(--border)] bg-[var(--page)] px-3 py-1 text-xs font-medium hover:bg-[var(--glass-surface)] disabled:opacity-50"
                >
                  {panel.running ? "Running…" : "Run"}
                </button>

                {panel.error && (
                  <p className="mt-2 text-xs text-[var(--status-critical)]">{panel.error}</p>
                )}

                {panel.result && (
                  <div className="mt-3 border-t border-[var(--glass-border)] pt-2">
                    <div className="grid grid-cols-3 gap-x-2 gap-y-1 text-xs">
                      <Stat label="Trades" value={panel.result.metrics.total_trades.toLocaleString("en-IN")} />
                      <Stat label="Win %" value={fmtPercent(panel.result.metrics.win_rate)} />
                      <Stat label="PF" value={fmtNumber(panel.result.metrics.profit_factor)} />
                      <Stat label="Net P&L" value={fmtCurrency(panel.result.metrics.total_pnl)} />
                      <Stat label="Sharpe" value={fmtNumber(panel.result.metrics.sharpe_ratio)} />
                      <Stat label="Max DD %" value={fmtPercent(panel.result.metrics.max_drawdown_pct)} />
                    </div>
                    {panel.result.saved_result_id !== undefined && (
                      <p className="mt-2 text-[10px] text-[var(--ink-muted)]">
                        Saved to Analysis tab (result #{panel.result.saved_result_id})
                      </p>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[var(--ink-muted)]">{label}</div>
      <div className="font-medium text-[var(--ink-primary)]">{value}</div>
    </div>
  )
}
