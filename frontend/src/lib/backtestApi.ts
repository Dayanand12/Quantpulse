import type {
  BacktestResultDetail,
  BacktestResultSummary,
  BacktestRunConfig,
  BacktestRunResult,
  StrategyInfo,
} from "./backtestTypes"
import { API_BASE } from "./config"

// Same relative-path-through-the-dev-proxy pattern as lib/api.ts —
// /api/backtest/* routes to the standalone backtest_server.py process
// (see frontend/vite.config.ts), not the main live-trading backend.

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`)
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? `${path} -> ${res.status}`)
  }
  return res.json() as Promise<T>
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? `${path} -> ${res.status}`)
  }
  return res.json() as Promise<T>
}

export const backtestApi = {
  strategies: () => getJSON<StrategyInfo[]>("/api/backtest/strategies"),
  watchlist: () => getJSON<{ symbols: string[] }>("/api/backtest/watchlist"),
  run: (config: BacktestRunConfig) => postJSON<BacktestRunResult>("/api/backtest/run", config),
  cloneStrategy: (baseStrategy: string, newName: string) =>
    postJSON<StrategyInfo>("/api/backtest/strategies/clone", {
      base_strategy: baseStrategy,
      new_name: newName,
    }),
  // The Analysis tab's data source — every backtest run ever logged for a
  // strategy (see backtest_server.py's auto-save on /api/backtest/run),
  // deduplicated by parameters so re-running the same config never shows
  // up twice.
  results: (strategy: string) =>
    getJSON<BacktestResultSummary[]>(`/api/backtest/results?strategy=${encodeURIComponent(strategy)}`),
  resultDetail: (id: number) => getJSON<BacktestResultDetail>(`/api/backtest/results/${id}`),
}
