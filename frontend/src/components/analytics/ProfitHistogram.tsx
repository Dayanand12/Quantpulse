import type { HistogramBucket } from "../../lib/types"
import { EmptyState } from "./EmptyState"

export function ProfitHistogram({ buckets }: { buckets: HistogramBucket[] }) {
  if (buckets.length === 0) {
    return (
      <EmptyState
        title="No trades yet"
        subtitle="The per-trade P&L distribution will appear here."
      />
    )
  }

  const maxCount = Math.max(...buckets.map((b) => b.count), 1)

  return (
    <div className="flex h-[220px] items-end gap-1">
      {buckets.map((b, i) => {
        const heightPct = (b.count / maxCount) * 100
        const midpoint = (b.range_start + b.range_end) / 2
        const positive = midpoint >= 0

        return (
          <div key={i} className="group relative flex flex-1 flex-col items-center justify-end">
            {b.count > 0 && (
              <div className="pointer-events-none absolute bottom-full mb-1.5 hidden whitespace-nowrap rounded-md border border-[var(--glass-border)] bg-[var(--surface-2)] px-2 py-1 text-[10px] text-[var(--ink-secondary)] group-hover:block">
                ₹{Math.round(b.range_start).toLocaleString("en-IN")} to ₹
                {Math.round(b.range_end).toLocaleString("en-IN")} · {b.count} trade
                {b.count === 1 ? "" : "s"}
              </div>
            )}
            <div
              className="w-full rounded-t-md transition-all duration-300"
              style={{
                height: `${Math.max(heightPct, b.count > 0 ? 3 : 0)}%`,
                background: positive ? "#34d399" : "#ef5a5a",
                opacity: 0.85,
              }}
            />
          </div>
        )
      })}
    </div>
  )
}
