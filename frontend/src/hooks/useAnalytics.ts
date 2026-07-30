import { useEffect, useState } from "react"
import { api } from "../lib/api"
import type { AnalyticsFilters, AnalyticsSummary } from "../lib/types"

const DEFAULT_FILTERS: AnalyticsFilters = { timeframe: "daily" }

// Debounces filter changes (typing a symbol search, dragging a date) into
// a single request instead of one per keystroke.
const DEBOUNCE_MS = 250

export function useAnalytics() {
  const [filters, setFilters] = useState<AnalyticsFilters>(DEFAULT_FILTERS)
  const [data, setData] = useState<AnalyticsSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    const timer = setTimeout(() => {
      api
        .analyticsSummary(filters)
        .then((res) => {
          if (!cancelled) setData(res)
        })
        .catch(() => {
          if (!cancelled) setError("Failed to load analytics.")
        })
        .finally(() => {
          if (!cancelled) setLoading(false)
        })
    }, DEBOUNCE_MS)

    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [filters])

  function resetFilters() {
    setFilters(DEFAULT_FILTERS)
  }

  return { filters, setFilters, resetFilters, data, loading, error }
}
