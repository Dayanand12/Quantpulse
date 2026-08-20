import type {
  AnalyticsFilters,
  AnalyticsSummary,
  ChargeConfig,
  Deployment,
  DeploymentInput,
  MarketAnalysis,
  ScreenerRow,
  StrategyInfo,
  StrategySource,
  SymbolSuggestion,
  Trade,
  Watchlist,
} from "./types"
import { API_BASE } from "./config"

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`)
  if (!res.ok) {
    throw new Error(`${path} -> ${res.status}`)
  }
  return res.json() as Promise<T>
}

async function sendJSON<T>(path: string, method: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
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

  watchlists: () => getJSON<Watchlist[]>("/api/watchlists"),
  createWatchlist: (name: string) => sendJSON<Watchlist>("/api/watchlists", "POST", { name }),
  renameWatchlist: (id: number, name: string) =>
    sendJSON<Watchlist>(`/api/watchlists/${id}`, "PUT", { name }),
  saveWatchlistSymbols: (id: number, symbols: string[]) =>
    sendJSON<Watchlist>(`/api/watchlists/${id}/symbols`, "PUT", { symbols }),
  deleteWatchlist: (id: number) =>
    sendJSON<{ deleted: number }>(`/api/watchlists/${id}`, "DELETE"),

  searchSymbols: (query: string) =>
    getJSON<SymbolSuggestion[]>(`/api/symbols/search?q=${encodeURIComponent(query)}`),
  resyncSymbols: () => sendJSON<{ count: number }>("/api/symbols/resync", "POST"),

  strategies: () => getJSON<StrategyInfo[]>("/api/strategies"),

  strategySourceFiles: () => getJSON<string[]>("/api/strategy-source"),
  strategySource: (name: string) => getJSON<StrategySource>(`/api/strategy-source/${name}`),
  createStrategySource: (name: string, source: string) =>
    sendJSON<StrategySource>("/api/strategy-source", "POST", { name, source }),
  saveStrategySource: (name: string, source: string) =>
    sendJSON<StrategySource>(`/api/strategy-source/${name}`, "PUT", { source }),

  analyticsSummary: (filters: AnalyticsFilters) => {
    const params = new URLSearchParams({ timeframe: filters.timeframe })
    if (filters.strategy) params.set("strategy", filters.strategy)
    if (filters.symbol) params.set("symbol", filters.symbol)
    if (filters.date_from) params.set("date_from", filters.date_from)
    if (filters.date_to) params.set("date_to", filters.date_to)
    return getJSON<AnalyticsSummary>(`/api/analytics/summary?${params.toString()}`)
  },

  trades: (params?: {
    today?: boolean
    strategy?: string
    deployment_id?: string
    symbol?: string
    date_from?: string
    date_to?: string
  }) => {
    const search = new URLSearchParams()
    if (params?.today) search.set("today", "true")
    if (params?.strategy) search.set("strategy", params.strategy)
    if (params?.deployment_id) search.set("deployment_id", params.deployment_id)
    if (params?.symbol) search.set("symbol", params.symbol)
    if (params?.date_from) search.set("date_from", params.date_from)
    if (params?.date_to) search.set("date_to", params.date_to)
    const qs = search.toString()
    return getJSON<Trade[]>(`/api/trades${qs ? `?${qs}` : ""}`)
  },

  deployments: () => getJSON<Deployment[]>("/api/deployments"),
  createDeployment: (input: DeploymentInput) =>
    sendJSON<Deployment>("/api/deployments", "POST", input),
  updateDeployment: (id: string, input: DeploymentInput) =>
    sendJSON<Deployment>(`/api/deployments/${id}`, "PUT", input),
  deleteDeployment: (id: string) =>
    sendJSON<{ deleted: string }>(`/api/deployments/${id}`, "DELETE"),

  instrumentRefs: (symbols: string[]) =>
    getJSON<Record<string, { instrument_token: number; exchange: string } | null>>(
      `/api/instrument-refs?symbols=${encodeURIComponent(symbols.join(","))}`,
    ),

  chargeConfig: () => getJSON<ChargeConfig>("/api/settings/charges"),
  saveChargeConfig: (config: ChargeConfig) =>
    sendJSON<ChargeConfig>("/api/settings/charges", "PUT", config),
}
