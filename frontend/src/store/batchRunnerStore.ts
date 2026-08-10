import { create } from "zustand"
import { backtestApi } from "../lib/backtestApi"
import type { BacktestRunConfig, BatchPanelResult } from "../lib/backtestTypes"
import { playBacktestCompleteSound } from "../lib/notifySound"

// Module-level Zustand store (same pattern as liveStore.ts) instead of
// React state owned by BatchRunner.tsx — a batch run (up to 6 panels x N
// symbols) can take well over a minute, and React Router unmounts the
// Backtest page's whole component tree on navigation. Local useState was
// getting thrown away the moment the user switched to another page, so
// even though the backend kept running and saved the result fine (it has
// no idea the browser navigated anywhere), the panel came back looking
// empty/reset on return — reading as "did it stop?" Lifting state here
// means it survives navigation exactly like the live WebSocket feed does.
const PANEL_COUNT = 6

export interface BatchPanelState {
  label: string
  overridesText: string
  result: BatchPanelResult | null
  running: boolean
  error: string | null
}

function emptyPanel(index: number): BatchPanelState {
  return { label: `Panel ${index + 1}`, overridesText: "{}", result: null, running: false, error: null }
}

interface BatchRunnerState {
  // Which strategy the current `panels` belong to — lets the store tell
  // "same strategy, just navigated back" (keep panels/results as-is) apart
  // from "switched to a different strategy" (reseed with fresh defaults).
  strategy: string
  panels: BatchPanelState[]
  runningAll: boolean
  globalError: string | null

  ensureSeededForStrategy: (strategy: string) => void
  updatePanel: (index: number, patch: Partial<BatchPanelState>) => void
  runIndices: (strategy: string, sharedConfig: BacktestRunConfig, indices: number[]) => Promise<void>
  runAll: (strategy: string, sharedConfig: BacktestRunConfig) => Promise<void>
}

function parseOverrides(text: string): Record<string, number> {
  const parsed = JSON.parse(text)
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("Overrides must be a JSON object of {parameter_name: value}.")
  }
  return parsed as Record<string, number>
}

export const useBatchRunnerStore = create<BatchRunnerState>((set, get) => ({
  strategy: "",
  panels: Array.from({ length: PANEL_COUNT }, (_, i) => emptyPanel(i)),
  runningAll: false,
  globalError: null,

  ensureSeededForStrategy: (strategy) => {
    if (!strategy || get().strategy === strategy) return // same strategy as last time — keep panels/results

    set({
      strategy,
      panels: Array.from({ length: PANEL_COUNT }, (_, i) => emptyPanel(i)),
      globalError: null,
    })

    backtestApi
      .strategyParams(strategy)
      .then((res) => {
        if (!res.raw_json || get().strategy !== strategy) return // strategy changed again mid-fetch
        let parametersText = "{}"
        try {
          const parsed = JSON.parse(res.raw_json) as { parameters?: Record<string, number> }
          parametersText = JSON.stringify(parsed.parameters ?? {}, null, 2)
        } catch {
          // malformed conditions.json is surfaced elsewhere (StrategyParamsEditor)
        }
        set((state) => ({
          panels: state.panels.map((p) => ({ ...p, overridesText: parametersText })),
        }))
      })
      .catch(() => {
        /* strategy has no params file (e.g. orb_reversal) — panels stay at "{}" */
      })
  },

  updatePanel: (index, patch) => {
    set((state) => ({
      panels: state.panels.map((p, i) => (i === index ? { ...p, ...patch } : p)),
    }))
  },

  runIndices: async (strategy, sharedConfig, indices) => {
    set({ globalError: null })
    const { panels, updatePanel } = get()

    const requestPanels: { label: string; overrides: Record<string, number> }[] = []
    const validIndices: number[] = []
    for (const i of indices) {
      try {
        const overrides = parseOverrides(panels[i].overridesText)
        requestPanels.push({ label: panels[i].label, overrides })
        validIndices.push(i)
        updatePanel(i, { running: true, error: null })
      } catch (e) {
        updatePanel(i, { error: e instanceof Error ? e.message : "Invalid JSON.", running: false })
      }
    }
    if (requestPanels.length === 0) return

    try {
      const res = await backtestApi.runBatch({
        strategy,
        panels: requestPanels,
        symbols: sharedConfig.symbols,
        timeframe: sharedConfig.timeframe,
        quantity: sharedConfig.quantity,
        stoploss_pct: sharedConfig.stoploss_pct,
        target_pct: sharedConfig.target_pct,
        trailing_pct: sharedConfig.trailing_pct,
        max_cycles_per_day: sharedConfig.max_cycles_per_day,
        start_time: sharedConfig.start_time,
        end_time: sharedConfig.end_time,
        capital: sharedConfig.capital,
        charges: sharedConfig.charges,
        date_from: sharedConfig.date_from,
        date_to: sharedConfig.date_to,
        save: true,
      })

      // Only apply results if the store is still showing this strategy —
      // if the user switched strategies mid-run, ensureSeededForStrategy
      // already reset `panels`, and slotting a stale response back in
      // would silently attribute one strategy's results to another.
      if (get().strategy !== strategy) return

      set((state) => ({
        panels: state.panels.map((p, i) => {
          const slot = validIndices.indexOf(i)
          if (slot === -1) return p
          return { ...p, result: res.panels[slot], running: false, error: null }
        }),
      }))
    } catch (e) {
      const message = e instanceof Error ? e.message : "Batch run failed."
      if (get().strategy === strategy) {
        set({ globalError: message })
        set((state) => ({
          panels: state.panels.map((p, i) =>
            validIndices.includes(i) ? { ...p, running: false, error: message } : p,
          ),
        }))
      }
    } finally {
      playBacktestCompleteSound()
    }
  },

  runAll: async (strategy, sharedConfig) => {
    set({ runningAll: true })
    await get().runIndices(strategy, sharedConfig, get().panels.map((_, i) => i))
    set({ runningAll: false })
  },
}))
