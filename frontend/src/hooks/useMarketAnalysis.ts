import { useEffect, useState } from "react"
import { api } from "../lib/api"
import type { MarketAnalysis as MarketAnalysisData } from "../lib/types"

const POLL_MS = 5000

// Shared by the fixed NIFTY 50 / BANK NIFTY "Today's Read" cards and the
// free-text symbol search box — same poll-every-5s pattern, one place.
export function useMarketAnalysis(symbol: string) {
  const [data, setData] = useState<MarketAnalysisData | null>(null)

  useEffect(() => {
    let cancelled = false
    setData(null)

    async function poll() {
      try {
        const result = await api.marketAnalysis(symbol)
        if (!cancelled) setData(result)
      } catch {
        if (!cancelled) setData({ error: "Failed to reach backend." })
      }
    }

    poll()
    const id = setInterval(poll, POLL_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [symbol])

  return data
}
