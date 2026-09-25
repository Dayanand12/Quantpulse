import { useEffect, useState } from "react"
import { api } from "../lib/api"
import type { AnalyticsFilters, AnalyticsSummary } from "../lib/types"

// Local (not UTC) date, so this matches the trading day the user is
// actually in rather than flipping early/late depending on timezone.
function todayISO(): string {
  const d = new Date()
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, "0")
  const day = String(d.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

function defaultFilters(): AnalyticsFilters {
  const today = todayISO()
  return { timeframe: "daily", date_from: today, date_to: today }
}

// Debounces filter changes (typing a symbol search, dragging a date) into
// a single request instead of one per keystroke.
const DEBOUNCE_MS = 250

export function useAnalytics() {
  const [filters, setFilters] = useState<AnalyticsFilters>(defaultFilters)
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
    setFilters(defaultFilters())
  }

  return { filters, setFilters, resetFilters, data, loading, error }
}
