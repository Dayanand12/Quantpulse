import { useEffect, useState } from "react"
import { api } from "../lib/api"
import type { Watchlist } from "../lib/types"
import { SymbolAutocomplete } from "./SymbolAutocomplete"

type Status = "loading" | "idle" | "saving" | "saved" | "error"
type ResyncStatus = "idle" | "syncing" | "done" | "error"

export function WatchlistEditor() {
  const [watchlists, setWatchlists] = useState<Watchlist[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [symbols, setSymbols] = useState<string[]>([])
  const [status, setStatus] = useState<Status>("loading")
  const [error, setError] = useState<string | null>(null)
  const [newWatchlistName, setNewWatchlistName] = useState("")
  const [renaming, setRenaming] = useState(false)
  const [renameValue, setRenameValue] = useState("")
  const [resyncStatus, setResyncStatus] = useState<ResyncStatus>("idle")
  const [resyncCount, setResyncCount] = useState<number | null>(null)

  useEffect(() => {
    api
      .watchlists()
      .then((all) => {
        setWatchlists(all)
        if (all.length > 0) {
          setSelectedId(all[0].id)
          setSymbols(all[0].symbols)
        }
        setStatus("idle")
      })
      .catch(() => {
        setError("Failed to load watchlists.")
        setStatus("error")
      })
  }, [])

  const selected = watchlists.find((w) => w.id === selectedId) ?? null

  function selectWatchlist(watchlist: Watchlist) {
    setSelectedId(watchlist.id)
    setSymbols(watchlist.symbols)
    setStatus("idle")
    setError(null)
    setRenaming(false)
  }

  function addSymbol(symbol: string) {
    setSymbols((prev) => (prev.includes(symbol) ? prev : [...prev, symbol]))
  }

  function removeSymbol(symbol: string) {
    setSymbols((prev) => prev.filter((s) => s !== symbol))
  }

  async function saveSymbols() {
    if (selectedId === null) return
    setStatus("saving")
    setError(null)
    try {
      const result = await api.saveWatchlistSymbols(selectedId, symbols)
      setSymbols(result.symbols)
      setWatchlists((prev) => prev.map((w) => (w.id === result.id ? result : w)))
      setStatus("saved")
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save watchlist.")
      setStatus("error")
    }
  }

  async function createWatchlist() {
    const name = newWatchlistName.trim()
    if (!name) return
    try {
      const created = await api.createWatchlist(name)
      setWatchlists((prev) => [...prev, created])
      setNewWatchlistName("")
      selectWatchlist(created)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create watchlist.")
      setStatus("error")
    }
  }

  async function renameSelected() {
    if (selectedId === null) return
    const name = renameValue.trim()
    if (!name) return
    try {
      const renamed = await api.renameWatchlist(selectedId, name)
      setWatchlists((prev) => prev.map((w) => (w.id === renamed.id ? renamed : w)))
      setRenaming(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to rename watchlist.")
      setStatus("error")
    }
  }

  async function deleteSelected() {
    if (selectedId === null || !selected) return
    if (!confirm(`Delete watchlist "${selected.name}"? This can't be undone.`)) return
    try {
      await api.deleteWatchlist(selectedId)
      const remaining = watchlists.filter((w) => w.id !== selectedId)
      setWatchlists(remaining)
      if (remaining.length > 0) selectWatchlist(remaining[0])
      else {
        setSelectedId(null)
        setSymbols([])
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete watchlist.")
      setStatus("error")
    }
  }

  async function resync() {
    setResyncStatus("syncing")
    try {
      const { count } = await api.resyncSymbols()
      setResyncCount(count)
      setResyncStatus("done")
    } catch {
      setResyncStatus("error")
    }
  }

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5">
      <div className="mb-1 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-[var(--ink-secondary)]">Watchlists</h2>
        <button
          onClick={resync}
          disabled={resyncStatus === "syncing"}
          className="text-xs text-[var(--ink-muted)] underline decoration-dotted hover:text-[var(--ink-secondary)] disabled:opacity-50"
        >
          {resyncStatus === "syncing"
            ? "Resyncing NSE symbols…"
            : resyncStatus === "done"
              ? `Resynced (${resyncCount} symbols) — resync again`
              : resyncStatus === "error"
                ? "Resync failed — try again"
                : "Resync NSE symbols for suggestions"}
        </button>
      </div>
      <p className="mb-4 text-xs text-[var(--ink-muted)]">
        Every watchlist's symbols are streamed and tradeable together — these are just for
        organizing what you pick from. Restart the backend for changes to take effect.
      </p>

      {status === "loading" ? (
        <p className="text-sm text-[var(--ink-muted)]">Loading…</p>
      ) : (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-2">
            {watchlists.map((w) => (
              <button
                key={w.id}
                onClick={() => selectWatchlist(w)}
                className="rounded-full px-3 py-1 text-xs font-medium"
                style={{
                  background: w.id === selectedId ? "var(--accent)" : "var(--surface-2)",
                  color: w.id === selectedId ? "white" : "var(--ink-secondary)",
                }}
              >
                {w.name} ({w.symbols.length})
              </button>
            ))}
            <input
              value={newWatchlistName}
              onChange={(e) => setNewWatchlistName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && createWatchlist()}
              placeholder="New watchlist name"
              className="w-40 rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-2 py-1 text-xs outline-none focus:border-[var(--accent)]"
            />
            <button
              onClick={createWatchlist}
              className="rounded-md border border-[var(--border)] px-2 py-1 text-xs hover:bg-[var(--surface-2)]"
            >
              + Create
            </button>
          </div>

          {selected && (
            <>
              <div className="mb-3 flex items-center gap-2">
                {renaming ? (
                  <>
                    <input
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && renameSelected()}
                      autoFocus
                      className="rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-2 py-1 text-sm outline-none focus:border-[var(--accent)]"
                    />
                    <button onClick={renameSelected} className="text-xs text-[var(--accent)]">
                      Save name
                    </button>
                    <button
                      onClick={() => setRenaming(false)}
                      className="text-xs text-[var(--ink-muted)]"
                    >
                      Cancel
                    </button>
                  </>
                ) : (
                  <>
                    <span className="text-sm font-medium">{selected.name}</span>
                    <button
                      onClick={() => {
                        setRenaming(true)
                        setRenameValue(selected.name)
                      }}
                      className="text-xs text-[var(--ink-muted)] underline decoration-dotted hover:text-[var(--ink-secondary)]"
                    >
                      Rename
                    </button>
                    {watchlists.length > 1 && (
                      <button
                        onClick={deleteSelected}
                        className="text-xs text-[var(--status-critical)] underline decoration-dotted"
                      >
                        Delete
                      </button>
                    )}
                  </>
                )}
              </div>

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
                <SymbolAutocomplete onSelect={addSymbol} />
                <button
                  onClick={saveSymbols}
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
            </>
          )}

          {error && <p className="mt-2 text-xs text-[var(--status-critical)]">{error}</p>}
        </>
      )}
    </div>
  )
}
