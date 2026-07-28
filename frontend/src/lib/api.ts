import type {
  Deployment,
  DeploymentInput,
  MarketAnalysis,
  ScreenerRow,
  StrategyInfo,
  StrategySource,
  Watchlist,
} from "./types"

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) {
    throw new Error(`${path} -> ${res.status}`)
  }
  return res.json() as Promise<T>
}

async function sendJSON<T>(path: string, method: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? `${path} -> ${res.status}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  screenerLive: () => getJSON<ScreenerRow[]>("/api/screener-live"),
  marketAnalysis: (symbol: string) =>
    getJSON<MarketAnalysis>(`/api/market-analysis?symbol=${encodeURIComponent(symbol)}`),
  downloadReport: (symbol: string) =>
    getJSON<{ file: string }>(`/api/download-report?symbol=${encodeURIComponent(symbol)}`),

  watchlist: () => getJSON<Watchlist>("/api/watchlist"),
  saveWatchlist: (symbols: string[]) => sendJSON<Watchlist>("/api/watchlist", "PUT", { symbols }),

  strategies: () => getJSON<StrategyInfo[]>("/api/strategies"),

  strategySourceFiles: () => getJSON<string[]>("/api/strategy-source"),
  strategySource: (name: string) => getJSON<StrategySource>(`/api/strategy-source/${name}`),
  createStrategySource: (name: string, source: string) =>
    sendJSON<StrategySource>("/api/strategy-source", "POST", { name, source }),
  saveStrategySource: (name: string, source: string) =>
    sendJSON<StrategySource>(`/api/strategy-source/${name}`, "PUT", { source }),

  deployments: () => getJSON<Deployment[]>("/api/deployments"),
  createDeployment: (input: DeploymentInput) =>
    sendJSON<Deployment>("/api/deployments", "POST", input),
  updateDeployment: (id: string, input: DeploymentInput) =>
    sendJSON<Deployment>(`/api/deployments/${id}`, "PUT", input),
  deleteDeployment: (id: string) =>
    sendJSON<{ deleted: string }>(`/api/deployments/${id}`, "DELETE"),
}
