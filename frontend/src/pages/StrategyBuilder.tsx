import { useEffect, useState } from "react"
import CodeMirror from "@uiw/react-codemirror"
import { python } from "@codemirror/lang-python"
import { api } from "../lib/api"

const TEMPLATE = `from typing import Dict, List

from core.application.interfaces.strategy import IStrategy
from core.domain.enums import OrderSide


class MyStrategy(IStrategy):
    # Unique id — this is what you select when deploying on the
    # Strategies page. Lowercase letters, digits, underscores only.
    name = "my_strategy"
    display_name = "My Strategy"
    side = OrderSide.SELL  # or OrderSide.BUY

    def screen(self, snapshot: Dict[str, dict], symbols: List[str]) -> List[str]:
        """Return the subset of \`symbols\` this strategy wants to enter now.

        snapshot[symbol] is a dict with: ltp, ema9, ema21, rsi, adx,
        atr_pct, vwap, volume_ratio, orb_low, distance_to_or_low.
        Risk/sizing (quantity, SL%, target%, trailing%, max cycles) is set
        per-deployment on the Strategies page, not here.
        """
        candidates = []
        for symbol in symbols:
            data = snapshot.get(symbol)
            if not data:
                continue
            # TODO: your entry condition here
            candidates.append(symbol)
        return candidates
`

type Mode = "view" | "create"
type Status = "idle" | "saving" | "saved" | "error"

export function StrategyBuilder() {
  const [files, setFiles] = useState<string[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [source, setSource] = useState("")
  const [mode, setMode] = useState<Mode>("view")
  const [newName, setNewName] = useState("")
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [status, setStatus] = useState<Status>("idle")
  const [statusError, setStatusError] = useState<string | null>(null)

  async function loadFiles(preferred?: string) {
    const fileList = await api.strategySourceFiles()
    setFiles(fileList)

    const target = preferred ?? fileList[0]
    if (target) {
      await openFile(target)
    }
  }

  async function openFile(name: string) {
    const body = await api.strategySource(name)
    setSelected(name)
    setSource(body.source)
    setMode("view")
    setStatus("idle")
    setStatusError(null)
  }

  useEffect(() => {
    loadFiles("orb_reversal")
      .catch(() => setLoadError("Failed to load strategies."))
      .finally(() => setLoading(false))
  }, [])

  function startNewStrategy() {
    setMode("create")
    setSelected(null)
    setNewName("")
    setSource(TEMPLATE)
    setStatus("idle")
    setStatusError(null)
  }

  async function handleSave() {
    setStatus("saving")
    setStatusError(null)
    try {
      if (mode === "create") {
        const name = newName.trim()
        if (!name) {
          throw new Error("Enter a name for the new strategy.")
        }
        await api.createStrategySource(name, source)
        await loadFiles(name)
      } else if (selected) {
        await api.saveStrategySource(selected, source)
        await loadFiles(selected)
      }
      setStatus("saved")
    } catch (e) {
      setStatusError(e instanceof Error ? e.message : "Failed to save.")
      setStatus("error")
    }
  }

  if (loading) {
    return <p className="text-sm text-[var(--ink-muted)]">Loading…</p>
  }

  return (
    <div className="flex h-full flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Strategy Builder</h1>
        <button
          onClick={startNewStrategy}
          className="rounded-md bg-[var(--accent)] px-4 py-1.5 text-sm font-medium text-white"
        >
          New Strategy
        </button>
      </div>
      {loadError && <p className="text-sm text-[var(--status-critical)]">{loadError}</p>}

      <div className="grid grid-cols-[200px_1fr] gap-4">
        <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3">
          <div className="mb-2 text-xs font-semibold text-[var(--ink-secondary)]">Files</div>
          <div className="flex flex-col gap-1">
            {files.map((name) => (
              <button
                key={name}
                onClick={() => openFile(name)}
                className="rounded-md px-2 py-1.5 text-left text-sm"
                style={{
                  background:
                    mode === "view" && selected === name ? "var(--surface-2)" : "transparent",
                  color:
                    mode === "view" && selected === name
                      ? "var(--ink-primary)"
                      : "var(--ink-secondary)",
                }}
              >
                {name}.py
              </button>
            ))}
            {mode === "create" && (
              <div className="rounded-md bg-[var(--surface-2)] px-2 py-1.5 text-sm text-[var(--accent)]">
                (new file)
              </div>
            )}
          </div>
        </div>

        <div className="flex flex-col gap-3">
          {mode === "create" ? (
            <div className="flex items-center gap-2">
              <span className="text-xs text-[var(--ink-muted)]">Name:</span>
              <input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="e.g. ema_crossover"
                className="w-64 rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5 text-sm outline-none focus:border-[var(--accent)]"
              />
              <span className="text-xs text-[var(--ink-muted)]">
                lowercase letters, digits, underscores only
              </span>
            </div>
          ) : (
            <div className="text-sm text-[var(--ink-secondary)]">
              {selected ? `${selected}.py` : "No file selected."}
            </div>
          )}

          <div className="overflow-hidden rounded-lg border border-[var(--border)]">
            <CodeMirror
              value={source}
              height="520px"
              theme="dark"
              extensions={[python()]}
              onChange={(value) => setSource(value)}
            />
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={handleSave}
              disabled={status === "saving" || (mode === "view" && !selected)}
              className="rounded-md bg-[var(--accent)] px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              {status === "saving" ? "Saving…" : mode === "create" ? "Create Strategy" : "Save"}
            </button>
            {status === "saved" && (
              <span className="text-xs text-[var(--status-good)]">
                Saved — restart the backend for it to be available for deployment.
              </span>
            )}
            {statusError && (
              <span className="text-xs text-[var(--status-critical)]">{statusError}</span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
