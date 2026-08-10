import { create } from "zustand"
import { DEFAULT_BACKTEST_CONFIG, type BacktestRunConfig, type BacktestRunResult } from "../lib/backtestTypes"

// Same reasoning as batchRunnerStore.ts: this used to be local useState in
// Backtest.tsx, which React Router throws away every time you navigate to
// another page. That's how a "my_strategy" (a leftover no-op test
// strategy with no conditions.json) ended up silently re-selected after
// coming back to /backtest — config.strategy reset to "" on remount,
// BacktestForm.tsx's "pick strategyList[0] when empty" effect fired again
// and picked whatever the API happens to return first, and
// BatchRunner.tsx's ensureSeededForStrategy saw that as a genuine strategy
// switch and wiped the panel view for the real strategy's still-running
// (or already finished) batch. Lifting the whole page's state here means
// navigating away and back leaves you looking at the same strategy,
// settings, and results you had.
interface BacktestPageState {
  config: BacktestRunConfig
  result: BacktestRunResult | null
  running: boolean
  error: string | null
  setConfig: (config: BacktestRunConfig) => void
  setResult: (result: BacktestRunResult | null) => void
  setRunning: (running: boolean) => void
  setError: (error: string | null) => void
}

export const useBacktestPageStore = create<BacktestPageState>((set) => ({
  config: DEFAULT_BACKTEST_CONFIG,
  result: null,
  running: false,
  error: null,
  setConfig: (config) => set({ config }),
  setResult: (result) => set({ result }),
  setRunning: (running) => set({ running }),
  setError: (error) => set({ error }),
}))
