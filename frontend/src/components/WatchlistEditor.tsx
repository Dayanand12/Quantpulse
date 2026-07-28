import { useEffect, useState } from "react"
import { api } from "../lib/api"

type Status = "loading" | "idle" | "saving" | "saved" | "error"

export function WatchlistEditor() {
  const [symbols, setSymbols] = useState<string[]>([])
  const [input, setInput] = useState("")
  const [status, setStatus] = useState<Status>("loading")
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .watchlist()
      .then((w) => {
        setSymbols(w.symbols)
        setStatus("idle")
      })
      .catch(() => {
        setError("Failed to load watchlist.")
        setStatus("error")
      })
  }, [])

  function addSymbol() {
    const cleaned = input.trim().toUpperCase()
    setInput("")
    if (!cleaned || symbols.includes(cleaned)) return
    setSymbols((prev) => [...prev, cleaned])
  }

  function removeSymbol(symbol: string) {
    setSymbols((prev) => prev.filter((s) => s !== symbol))
  }

  async function save() {
    setStatus("saving")
    setError(null)
    try {
      const result = await api.saveWatchlist(symbols)
      setSymbols(result.symbols)
      setStatus("saved")
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save watchlist.")
      setStatus("error")
    }
  }

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5">
      <h2 className="mb-1 text-sm font-semibold text-[var(--ink-secondary)]">Watchlist</h2>
      <p className="mb-4 text-xs text-[var(--ink-muted)]">
        Symbols the live engine tracks and trades. Restart the backend for changes to take
        effect.
      </p>

      {status === "loading" ? (
        <p className="text-sm text-[var(--ink-muted)]">Loading…</p>
      ) : (
        <>
          <div className="mb-4 flex flex-wrap gap-2">
            {symbols.length === 0 && (
              <span className="text-sm text-[var(--ink-muted)]">No symbols yet.</span>
            )}
            {symbols.map((symbol) => (
              <span
                key={symbol}
                className="flex items-center gap-1.5 rounded-full bg-[var(--surface-2)] px-3 py-1 text-sm"
              >
                {symbol}
                <button
                  onClick={() => removeSymbol(symbol)}
                  className="text-[var(--ink-muted)] hover:text-[var(--status-critical)]"
                  aria-label={`Remove ${symbol}`}
                >
                  ×
                </button>
              </span>
            ))}
          </div>

          <div className="flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addSymbol()}
              placeholder="e.g. RELIANCE"
              className="flex-1 rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5 text-sm outline-none focus:border-[var(--accent)]"
            />
            <button
              onClick={addSymbol}
              className="rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5 text-sm hover:bg-[var(--page)]"
            >
              Add
            </button>
            <button
              onClick={save}
              disabled={status === "saving"}
              className="rounded-md bg-[var(--accent)] px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              {status === "saving" ? "Saving…" : "Save Watchlist"}
            </button>
          </div>

          {status === "saved" && (
            <p className="mt-2 text-xs text-[var(--status-good)]">
              Saved — restart the backend to apply.
            </p>
          )}
          {error && <p className="mt-2 text-xs text-[var(--status-critical)]">{error}</p>}
        </>
      )}
    </div>
  )
}
