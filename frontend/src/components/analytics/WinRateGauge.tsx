export function WinRateGauge({ value }: { value: number | null }) {
  const size = 160
  const strokeWidth = 14
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const pct = value === null ? 0 : Math.max(0, Math.min(100, value))
  const offset = circumference * (1 - pct / 100)
  const color = value === null ? "var(--ink-muted)" : pct >= 50 ? "#34d399" : "#fab219"

  return (
    <div className="flex items-center justify-center py-2">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="var(--surface-2)"
            strokeWidth={strokeWidth}
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            style={{
              transition: "stroke-dashoffset 800ms cubic-bezier(0.16, 1, 0.3, 1), stroke 300ms ease",
            }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-3xl font-semibold tabular-nums text-[var(--ink-primary)]">
            {value === null ? "—" : `${value.toFixed(1)}%`}
          </span>
          <span className="text-xs text-[var(--ink-muted)]">Win Rate</span>
        </div>
      </div>
    </div>
  )
}
