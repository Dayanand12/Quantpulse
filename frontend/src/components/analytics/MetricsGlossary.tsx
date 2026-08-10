import { useState } from "react"
import { METRIC_CARDS } from "./SummaryCard"

// A permanent, always-readable version of each metric card's tooltip —
// hover tooltips are easy to miss (and don't really work on touch), and
// this exists specifically for someone who isn't already familiar with
// what these numbers mean. Reuses METRIC_CARDS' own text so the
// glossary can never drift out of sync with what the cards themselves say.
export function MetricsGlossary() {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] p-5 backdrop-blur-sm">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center gap-1.5 text-sm font-semibold text-[var(--ink-primary)]"
      >
        <span>{expanded ? "▾" : "▸"}</span>
        What do these numbers mean?
      </button>

      {expanded && (
        <dl className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
          {METRIC_CARDS.map((config) => (
            <div key={config.key}>
              <dt className="flex items-center gap-2 text-sm font-medium text-[var(--ink-primary)]">
                <span
                  className="flex h-6 w-6 items-center justify-center rounded-lg"
                  style={{
                    background: `color-mix(in srgb, var(${config.accent}) 18%, transparent)`,
                    color: `var(${config.accent})`,
                  }}
                >
                  <config.icon className="h-3.5 w-3.5" />
                </span>
                {config.label}
                {(config.goodLabel || config.badLabel) && (
                  <span className="text-[11px] font-normal text-[var(--ink-muted)]">
                    ({config.goodLabel ?? "higher"} = good, {config.badLabel ?? "lower"} = bad)
                  </span>
                )}
              </dt>
              <dd className="mt-1 text-xs leading-relaxed text-[var(--ink-secondary)]">
                {config.tooltip}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  )
}
