import { fmtCurrency } from "../lib/format"

export function PnlText({ value }: { value: number | null }) {
  if (value === null) {
    return <span className="tabular-nums text-[var(--ink-muted)]">—</span>
  }

  const color = value >= 0 ? "var(--status-good)" : "var(--status-critical)"
  const sign = value > 0 ? "+" : ""

  return (
    <span className="tabular-nums font-medium" style={{ color }}>
      {sign}
      {fmtCurrency(value)}
    </span>
  )
}
