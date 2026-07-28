import type { ReactNode } from "react"

interface StatTileProps {
  label: string
  value: ReactNode
  sub?: ReactNode
}

export function StatTile({ label, value, sub }: StatTileProps) {
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5">
      <div className="text-sm text-[var(--ink-muted)]">{label}</div>
      <div className="tabular-nums mt-1 text-2xl font-semibold text-[var(--ink-primary)]">
        {value}
      </div>
      {sub && <div className="mt-1 text-xs text-[var(--ink-secondary)]">{sub}</div>}
    </div>
  )
}
