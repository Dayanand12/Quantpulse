import { create } from "zustand"
import { api } from "../lib/api"
import type { Deployment, DeploymentInput, StrategyInfo, Watchlist } from "../lib/types"

// Shared across the Deployed Strategies and Available Strategies pages
// (same pattern as liveStore.ts / batchJobStore.ts) — both pages read the
// same strategies/watchlist/deployments lists and mutate the same
// deployments, so a plain per-page useState would mean every toggle/edit/
// delete only refreshed whichever page did it, leaving the other stale
// until its own next navigation-triggered refetch.
interface StrategiesState {
  strategies: StrategyInfo[]
  watchlist: string[]
  // Raw named watchlists (id/name/symbols) — for the "bind this deployment
  // to a watchlist" picker. `watchlist` above stays the flattened union,
  // still used by the manual-symbols picker.
  namedWatchlists: Watchlist[]
  deployments: Deployment[]
  loading: boolean
  loadError: string | null

  refresh: () => Promise<void>
  createDeployment: (input: DeploymentInput) => Promise<void>
  updateDeployment: (id: string, input: DeploymentInput) => Promise<void>
  toggleEnabled: (deployment: Deployment) => Promise<void>
  deleteDeployment: (id: string) => Promise<void>
}

export const useStrategiesStore = create<StrategiesState>((set, get) => ({
  strategies: [],
  watchlist: [],
  namedWatchlists: [],
  deployments: [],
  loading: true,
  loadError: null,

  refresh: async () => {
    try {
      const [strategies, watchlists, deployments] = await Promise.all([
        api.strategies(),
        api.watchlists(),
        api.deployments(),
      ])
      set({
        strategies,
        // A deployment can be built from any watchlist's symbols — see
        // server/main.py::_validate_deployment_request, which validates
        // against the union of every watchlist, not one specific list.
        watchlist: [...new Set(watchlists.flatMap((w) => w.symbols))],
        namedWatchlists: watchlists,
        deployments,
        loadError: null,
      })
    } catch {
      set({ loadError: "Failed to load strategies/deployments." })
    } finally {
      set({ loading: false })
    }
  },

  createDeployment: async (input) => {
    await api.createDeployment(input)
    await get().refresh()
  },

  updateDeployment: async (id, input) => {
    await api.updateDeployment(id, input)
    await get().refresh()
  },

  toggleEnabled: async (deployment) => {
    await api.updateDeployment(deployment.id, {
      strategy_name: deployment.strategy_name,
      symbols: deployment.symbols,
      watchlist_id: deployment.watchlist_id,
      capital: deployment.capital,
      quantity: deployment.quantity,
      stoploss_pct: deployment.stoploss_pct,
      target_pct: deployment.target_pct,
      trailing_pct: deployment.trailing_pct,
      max_cycles_per_day: deployment.max_cycles_per_day,
      enabled: !deployment.enabled,
      start_time: deployment.start_time,
      end_time: deployment.end_time,
      timeframe: deployment.timeframe,
    })
    await get().refresh()
  },

  deleteDeployment: async (id) => {
    await api.deleteDeployment(id)
    await get().refresh()
  },
}))

export function toDeploymentInput(d: Deployment): DeploymentInput {
  return {
    strategy_name: d.strategy_name,
    symbols: d.symbols,
    watchlist_id: d.watchlist_id,
    capital: d.capital,
    quantity: d.quantity,
    stoploss_pct: d.stoploss_pct,
    target_pct: d.target_pct,
    trailing_pct: d.trailing_pct,
    max_cycles_per_day: d.max_cycles_per_day,
    enabled: d.enabled,
    start_time: d.start_time,
    end_time: d.end_time,
    timeframe: d.timeframe,
  }
}
