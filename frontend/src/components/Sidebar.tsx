import { NavLink } from "react-router-dom"
import { useLiveStore } from "../store/liveStore"
import { ConnectionDot } from "./ConnectionDot"

const NAV_ITEMS = [
  { to: "/", label: "Live Dashboard", end: true },
  { to: "/positions", label: "Positions" },
  { to: "/trades", label: "Trades" },
  { to: "/performance", label: "Performance" },
  { to: "/screener", label: "Stock Screener" },
  { to: "/market-analysis", label: "Market Analysis" },
  { to: "/strategies", label: "Strategies" },
  { to: "/strategy-builder", label: "Strategy Builder" },
  { to: "/settings", label: "Settings" },
]

export function Sidebar() {
  const connected = useLiveStore((s) => s.connected)

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-[var(--border)] bg-[var(--surface)] p-5">
      <div className="mb-1 text-xl font-bold text-[var(--accent)]">QuantPulse</div>
      <div className="mb-6 text-xs text-[var(--ink-muted)]">Paper Trading Terminal</div>

      <nav className="flex flex-col gap-1">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              `rounded-md px-3 py-2 text-sm transition-colors ${
                isActive
                  ? "bg-[var(--surface-2)] text-[var(--ink-primary)]"
                  : "text-[var(--ink-secondary)] hover:bg-[var(--surface-2)] hover:text-[var(--ink-primary)]"
              }`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="mt-auto pt-6">
        <ConnectionDot connected={connected} />
      </div>
    </aside>
  )
}
