import { NavLink, Outlet } from "react-router-dom"

const TABS = [
  { to: "run", label: "Run" },
  { to: "analysis", label: "Analysis" },
]

// One sidebar entry ("Backtest") with two in-page tabs — Run (pick a
// strategy/symbols and run it, see BacktestRun.tsx) and Analysis (browse
// every stored equity result, see Analysis.tsx). Same pattern as
// pages/Strategies.tsx. The Options Backtest page (pages/OptionsBacktest.tsx)
// mirrors this exact structure for options instead of equities.
export function Backtest() {
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">Backtest</h1>

      <div className="flex gap-1 border-b border-[var(--border)]">
        {TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            className={({ isActive }) =>
              `-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? "border-[var(--accent)] text-[var(--ink-primary)]"
                  : "border-transparent text-[var(--ink-secondary)] hover:text-[var(--ink-primary)]"
              }`
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </div>

      <Outlet />
    </div>
  )
}
