import { useEffect } from "react"
import { Link } from "react-router-dom"
import { DeploymentCard } from "../components/DeploymentCard"
import { useStrategiesStore } from "../store/strategiesStore"

// "Deployed" tab of the Strategies page — enabled deployments, whether
// actually running or pending a backend restart. Disabled deployments and
// strategies that have never been deployed live on the "Available" tab
// instead (see AvailableStrategies.tsx / Strategies.tsx).
export function DeployedStrategies() {
  const strategies = useStrategiesStore((s) => s.strategies)
  const watchlist = useStrategiesStore((s) => s.watchlist)
  const namedWatchlists = useStrategiesStore((s) => s.namedWatchlists)
  const deployments = useStrategiesStore((s) => s.deployments)
  const loading = useStrategiesStore((s) => s.loading)
  const loadError = useStrategiesStore((s) => s.loadError)
  const refresh = useStrategiesStore((s) => s.refresh)

  useEffect(() => {
    refresh()
  }, [refresh])

  const deployed = deployments.filter((d) => d.enabled)

  if (loading) {
    return <p className="text-sm text-[var(--ink-muted)]">Loading…</p>
  }

  return (
    <div className="flex flex-col gap-6">
      {loadError && <p className="text-sm text-[var(--status-critical)]">{loadError}</p>}

      <section className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5">
        {deployed.length === 0 ? (
          <p className="text-sm text-[var(--ink-muted)]">
            Nothing deployed right now — head to the{" "}
            <Link to="/strategies/available" className="text-[var(--accent)] hover:underline">
              Available
            </Link>{" "}
            tab to deploy one.
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            {deployed.map((d) => (
              <DeploymentCard
                key={d.id}
                deployment={d}
                strategies={strategies}
                watchlist={watchlist}
                namedWatchlists={namedWatchlists}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
