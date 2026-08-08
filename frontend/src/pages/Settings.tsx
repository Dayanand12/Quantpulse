import { useEffect } from "react"
import { Link } from "react-router-dom"
import { useLiveStore } from "../store/liveStore"
import { StatTile } from "../components/StatTile"
import { ConnectionDot } from "../components/ConnectionDot"
import { WatchlistEditor } from "../components/WatchlistEditor"
import { ChargeConfigEditor } from "../components/ChargeConfigEditor"
import { fmtCurrency } from "../lib/format"

export function Settings() {
  const connect = useLiveStore((s) => s.connect)
  const connected = useLiveStore((s) => s.connected)
  const broker = useLiveStore((s) => s.brokerStatus)

  useEffect(() => {
    connect()
  }, [connect])

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">Settings</h1>

      <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5">
        <h2 className="mb-4 text-sm font-semibold text-[var(--ink-secondary)]">
          Paper Trading Account
        </h2>
        <div className="grid grid-cols-3 gap-4">
          <StatTile label="Available Capital" value={fmtCurrency(broker.available_capital)} />
          <StatTile label="Backend Connection" value={<ConnectionDot connected={connected} />} />
          <StatTile label="Mode" value="Paper (Simulated)" />
        </div>
        <p className="mt-4 text-sm text-[var(--ink-muted)]">
          Editable capital is planned for a later iteration. Strategy deployments (which
          symbols trade, how much capital, risk parameters) are managed on the{" "}
          <Link to="/strategies" className="text-[var(--accent)] hover:underline">
            Strategies
          </Link>{" "}
          page.
        </p>
      </div>

      <WatchlistEditor />
      <ChargeConfigEditor />
    </div>
  )
}
