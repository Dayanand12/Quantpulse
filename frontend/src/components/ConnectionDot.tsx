export function ConnectionDot({ connected }: { connected: boolean }) {
  const color = connected ? "var(--status-good)" : "var(--status-critical)"

  return (
    <div className="flex items-center gap-2 text-sm text-[var(--ink-secondary)]">
      <span
        className="h-2 w-2 rounded-full"
        style={{ background: color, boxShadow: `0 0 6px ${color}` }}
      />
      {connected ? "Live" : "Reconnecting…"}
    </div>
  )
}
