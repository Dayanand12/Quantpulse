import { create } from "zustand"
import { DEFAULT_BACKTEST_CONFIG, type BacktestRunConfig, type BacktestRunResult } from "../lib/backtestTypes"

// Same reasoning as backtestPageStore.ts: lifted out of local useState so
// navigating away (e.g. to check Analysis) and back doesn't reset the
// picked contract/strategy/result — see that store's comment for the
// exact past incident this pattern exists to avoid.
interface OptionsBacktestPageState {
  config: BacktestRunConfig
  // The OptionContractPicker's selection, kept separate from
  // config.symbols (which stays undefined until Run is actually clicked)
  // so switching strategy/timeframe/etc. doesn't require re-picking a
  // contract, and picking a new contract doesn't require re-entering risk
  // settings.
  contractSymbol: string
  result: BacktestRunResult | null
  running: boolean
  error: string | null
  // The most recent chain sweep's id (see ChainSweepPanel.tsx) — just the
  // id, not the whole ChainSweep, so navigating away mid-sweep and coming
  // back re-fetches fresh progress instead of showing a stale snapshot.
  sweepId: number | null
  setConfig: (config: BacktestRunConfig) => void
  setContractSymbol: (symbol: string) => void
  setResult: (result: BacktestRunResult | null) => void
  setRunning: (running: boolean) => void
  setError: (error: string | null) => void
  setSweepId: (id: number | null) => void
}

export const useOptionsBacktestPageStore = create<OptionsBacktestPageState>((set) => ({
  config: DEFAULT_BACKTEST_CONFIG,
  contractSymbol: "",
  result: null,
  running: false,
  error: null,
  sweepId: null,
  setConfig: (config) => set({ config }),
  setContractSymbol: (contractSymbol) => set({ contractSymbol }),
  setResult: (result) => set({ result }),
  setRunning: (running) => set({ running }),
  setError: (error) => set({ error }),
  setSweepId: (sweepId) => set({ sweepId }),
}))
