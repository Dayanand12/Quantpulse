const STAGE_STYLES: Record<string, { color: string; bg: string }> = {
  "Stage 1": { color: "var(--status-warning)", bg: "rgba(250, 178, 25, 0.12)" },
  "Stage 2": { color: "var(--status-serious)", bg: "rgba(236, 131, 90, 0.12)" },
  "Stage 3": { color: "var(--status-critical)", bg: "rgba(230, 103, 103, 0.14)" },
  None: { color: "var(--ink-muted)", bg: "transparent" },
}

export function StageBadge({ stage }: { stage: string }) {
  const style = STAGE_STYLES[stage] ?? STAGE_STYLES.None

  return (
    <span
      className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium"
      style={{ color: style.color, background: style.bg }}
    >
      {stage}
    </span>
  )
}
