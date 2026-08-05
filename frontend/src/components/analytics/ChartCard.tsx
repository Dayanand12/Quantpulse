import type { ReactNode } from "react"
import { ChartErrorBoundary } from "./ChartErrorBoundary"

interface ChartCardProps {
  title: string
  subtitle?: string
  action?: ReactNode
  children: ReactNode
}

// Shared glass chrome for every chart/table panel on the analytics page —
// one place to change the "premium card" look instead of 8 copies of it.
export function ChartCard({ title, subtitle, action, children }: ChartCardProps) {
  return (
    <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] p-5 shadow-[0_20px_40px_-28px_rgba(0,0,0,0.7)] backdrop-blur-sm">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-[var(--ink-primary)]">{title}</h3>
          {subtitle && <p className="mt-0.5 text-xs text-[var(--ink-muted)]">{subtitle}</p>}
        </div>
        {action}
      </div>
      <ChartErrorBoundary>{children}</ChartErrorBoundary>
    </div>
  )
}
