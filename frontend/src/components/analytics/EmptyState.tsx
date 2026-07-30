import { IconInbox } from "./icons"

export function EmptyState({
  title = "No trades yet",
  subtitle = "Once trades close under the current filters, this will fill in automatically.",
}: {
  title?: string
  subtitle?: string
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[var(--surface-2)] text-[var(--ink-muted)]">
        <IconInbox width={22} height={22} />
      </div>
      <p className="text-sm font-medium text-[var(--ink-secondary)]">{title}</p>
      <p className="max-w-xs text-xs text-[var(--ink-muted)]">{subtitle}</p>
    </div>
  )
}
