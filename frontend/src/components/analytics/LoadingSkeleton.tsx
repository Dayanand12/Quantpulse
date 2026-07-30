function shimmer(extraClass: string) {
  return (
    <div
      className={`animate-pulse rounded-lg bg-[var(--surface-2)] ${extraClass}`}
    />
  )
}

export function CardSkeleton() {
  return (
    <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] p-5">
      {shimmer("h-9 w-9 rounded-xl")}
      {shimmer("mt-4 h-3 w-20")}
      {shimmer("mt-2 h-7 w-24")}
    </div>
  )
}

export function ChartSkeleton({ height = 240 }: { height?: number }) {
  return (
    <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] p-5">
      {shimmer("h-4 w-32")}
      <div className="mt-4 animate-pulse rounded-lg bg-[var(--surface-2)]" style={{ height }} />
    </div>
  )
}

export function TableSkeleton() {
  return (
    <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] p-5">
      {shimmer("h-4 w-40")}
      <div className="mt-4 flex flex-col gap-2">
        {[0, 1, 2].map((i) => (
          <div key={i} className="animate-pulse rounded-lg bg-[var(--surface-2)]" style={{ height: 40 }} />
        ))}
      </div>
    </div>
  )
}
