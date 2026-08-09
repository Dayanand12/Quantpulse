import { useEffect, useState } from "react"
import { backtestApi } from "../../lib/backtestApi"

const textareaClass =
  "w-full rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 font-mono text-xs outline-none focus:border-[var(--accent)]"

interface StrategyParamsEditorProps {
  strategyName: string
}

// Raw JSON view/edit of a strategy's conditions.json (core/domain/
// strategy_conditions.py) — the indicator thresholds/conditions that used
// to be hardcoded constants in the strategy's .py file. Editing here and
// re-running immediately picks up the change (backtest_server.py reads
// the file fresh on every /run), and a different saved value produces a
// distinct, comparable row in the Analysis tab instead of silently
// overwriting the last one.
export function StrategyParamsEditor({ strategyName }: StrategyParamsEditorProps) {
  const [hasParams, setHasParams] = useState<boolean | null>(null)
  const [text, setText] = useState("")
  const [savedText, setSavedText] = useState("")
  const [status, setStatus] = useState<"idle" | "loading" | "saving" | "error">("loading")
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    setStatus("loading")
    setError(null)
    backtestApi
      .strategyParams(strategyName)
      .then((res) => {
        setHasParams(res.has_params)
        setText(res.raw_json ?? "")
        setSavedText(res.raw_json ?? "")
        setStatus("idle")
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : "Failed to load strategy params.")
        setStatus("error")
      })
  }, [strategyName])

  async function handleSave() {
    setStatus("saving")
    setError(null)
    try {
      const res = await backtestApi.saveStrategyParams(strategyName, text)
      setText(res.raw_json)
      setSavedText(res.raw_json)
      setStatus("idle")
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save — check the JSON is valid.")
      setStatus("error")
    }
  }

  if (hasParams === false) {
    return null // this strategy hasn't been migrated to condition-JSON yet
  }

  const dirty = text !== savedText

  return (
    <div className="mt-5 border-t border-[var(--glass-border)] pt-4">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center gap-1.5 text-xs font-medium text-[var(--ink-secondary)] hover:text-[var(--ink-primary)]"
      >
        <span>{expanded ? "▾" : "▸"}</span>
        Indicator Parameters {dirty && <span className="text-[var(--accent)]">(unsaved)</span>}
      </button>

      {expanded && (
        <div className="mt-2">
          {status === "loading" ? (
            <p className="text-xs text-[var(--ink-muted)]">Loading…</p>
          ) : (
            <>
              <p className="mb-2 text-xs text-[var(--ink-muted)]">
                Edit the thresholds/conditions this strategy screens on — "parameters" are the
                values you'd tune (e.g. adx_threshold); "conditions" is the rule structure itself.
                Saving here changes the actual strategy for its next run and any future deployment
                of it, same as editing the .py file used to.
              </p>
              <textarea
                className={textareaClass}
                rows={12}
                spellCheck={false}
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
              <div className="mt-2 flex items-center gap-3">
                <button
                  type="button"
                  onClick={handleSave}
                  disabled={status === "saving" || !dirty}
                  className="rounded-md bg-[var(--accent)] px-4 py-1.5 text-xs font-medium text-white disabled:opacity-50"
                >
                  {status === "saving" ? "Saving…" : "Save"}
                </button>
                {dirty && (
                  <button
                    type="button"
                    onClick={() => setText(savedText)}
                    className="text-xs text-[var(--ink-muted)] hover:text-[var(--ink-primary)]"
                  >
                    Revert
                  </button>
                )}
              </div>
              {error && <p className="mt-2 text-xs text-[var(--status-critical)]">{error}</p>}
            </>
          )}
        </div>
      )}
    </div>
  )
}
