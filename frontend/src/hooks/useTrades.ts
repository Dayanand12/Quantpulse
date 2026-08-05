import { useEffect, useState } from "react"
import { api } from "../lib/api"
import type { Trade } from "../lib/types"

// Persisted trade history (survives backend restarts) — polled rather than
// pushed over the live WebSocket, since re-sending the entire trade history
// every second wouldn't scale as it grows into the thousands. 15s keeps the
// Trades page / Live Dashboard reasonably fresh without hammering the DB.
const POLL_MS = 15_000

export function useTrades(options?: { today?: boolean }) {
  const today = options?.today ?? false
  const [trades, setTrades] = useState<Trade[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    function load() {
      api
        .trades({ today })
        .then((res) => {
          if (!cancelled) {
            setTrades(res)
            setError(null)
          }
        })
        .catch(() => {
          if (!cancelled) setError("Failed to load trades.")
        })
        .finally(() => {
          if (!cancelled) setLoading(false)
        })
    }

    load()
    const interval = setInterval(load, POLL_MS)

    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [today])

  return { trades, loading, error }
}
