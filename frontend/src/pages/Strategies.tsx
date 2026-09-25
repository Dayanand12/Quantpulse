import { NavLink, Outlet } from "react-router-dom"

const TABS = [
  { to: "deployed", label: "Deployed" },
  { to: "available", label: "Available" },
]

// One sidebar entry ("Strategies") with two in-page tabs — Deployed
// (enabled deployments, running or pending restart) and Available
// (disabled deployments, never-deployed strategies, and the "New
// Deployment" form). See DeployedStrategies.tsx / AvailableStrategies.tsx.
// Both tabs read/write the same strategiesStore, so switching tabs never
// loses in-flight state.
export function Strategies() {
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">Strategies</h1>

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
