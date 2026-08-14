import { useEffect, useState } from "react"
import { api } from "../lib/api"
import type { SymbolSuggestion } from "../lib/types"

interface SymbolAutocompleteProps {
  onSelect: (symbol: string) => void
  placeholder?: string
}

// Debounced typeahead over the NSE symbol master (GET /api/symbols/search).
// Falls back to plain free-text add on Enter (matching the old raw-input
// behavior) so index symbols like "NIFTY 50", or any symbol before a
// resync has ever been run, still work.
export function SymbolAutocomplete({ onSelect, placeholder }: SymbolAutocompleteProps) {
  const [text, setText] = useState("")
  const [suggestions, setSuggestions] = useState<SymbolSuggestion[]>([])
  const [open, setOpen] = useState(false)
  const [highlighted, setHighlighted] = useState(0)

  useEffect(() => {
    const query = text.trim()
    if (query.length < 1) {
      setSuggestions([])
      return
    }
    const timeout = setTimeout(() => {
      api
        .searchSymbols(query)
        .then((results) => {
          setSuggestions(results)
          setHighlighted(0)
        })
        .catch(() => setSuggestions([]))
    }, 200)
    return () => clearTimeout(timeout)
  }, [text])

  function commit(symbol: string) {
    const cleaned = symbol.trim().toUpperCase()
    if (!cleaned) return
    onSelect(cleaned)
    setText("")
    setSuggestions([])
    setOpen(false)
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault()
      if (open && suggestions[highlighted]) {
        commit(suggestions[highlighted].tradingsymbol)
      } else {
        commit(text)
      }
    } else if (e.key === "ArrowDown") {
      e.preventDefault()
      setHighlighted((i) => Math.min(i + 1, suggestions.length - 1))
    } else if (e.key === "ArrowUp") {
      e.preventDefault()
      setHighlighted((i) => Math.max(i - 1, 0))
    } else if (e.key === "Escape") {
      setOpen(false)
    }
  }

  return (
    <div className="relative flex-1">
      <input
        value={text}
        onChange={(e) => {
          setText(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
        placeholder={placeholder ?? "e.g. RELIANCE"}
        className="w-full rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5 text-sm outline-none focus:border-[var(--accent)]"
      />
      {open && suggestions.length > 0 && (
        <ul className="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-md border border-[var(--border)] bg-[var(--surface)] shadow-lg">
          {suggestions.map((s, i) => (
            <li key={s.tradingsymbol}>
              <button
                type="button"
                // onMouseDown (not onClick) fires before the input's onBlur,
                // so the click registers instead of the dropdown closing first.
                onMouseDown={(e) => {
                  e.preventDefault()
                  commit(s.tradingsymbol)
                }}
                className="flex w-full items-center justify-between gap-3 px-3 py-1.5 text-left text-sm hover:bg-[var(--surface-2)]"
                style={i === highlighted ? { background: "var(--surface-2)" } : undefined}
              >
                <span className="font-medium">{s.tradingsymbol}</span>
                <span className="truncate text-xs text-[var(--ink-muted)]">{s.name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
