import { useEffect, useRef, useState } from "react"
import { DeploymentCard } from "../components/DeploymentCard"
import { DeploymentFieldsForm, isDeploymentFormValid } from "../components/DeploymentFieldsForm"
import { useStrategiesStore } from "../store/strategiesStore"
import type { DeploymentInput } from "../lib/types"

const EMPTY_FORM: DeploymentInput = {
  strategy_name: "",
  symbols: [],
  watchlist_id: null,
  capital: 50000,
  quantity: 50,
  stoploss_pct: 0.8,
  target_pct: 2.0,
  trailing_pct: 0.1,
  max_cycles_per_day: 10,
  enabled: true,
  start_time: "09:20",
  end_time: "11:30",
  timeframe: "minute",
}

// "Available" tab of the Strategies page — everything that isn't
// currently live: disabled deployments (re-enable, edit, or delete them)
// plus strategy files with no deployment record at all, and the form for
// deploying a new one. Live (enabled) deployments live on the "Deployed"
// tab instead (see DeployedStrategies.tsx / Strategies.tsx).
export function AvailableStrategies() {
  const strategies = useStrategiesStore((s) => s.strategies)
  const watchlist = useStrategiesStore((s) => s.watchlist)
  const namedWatchlists = useStrategiesStore((s) => s.namedWatchlists)
  const deployments = useStrategiesStore((s) => s.deployments)
  const loading = useStrategiesStore((s) => s.loading)
  const loadError = useStrategiesStore((s) => s.loadError)
  const refresh = useStrategiesStore((s) => s.refresh)
  const createDeployment = useStrategiesStore((s) => s.createDeployment)

  const [form, setForm] = useState<DeploymentInput>(EMPTY_FORM)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const formRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => {
    setForm((f) => (f.strategy_name ? f : { ...f, strategy_name: strategies[0]?.name ?? "" }))
  }, [strategies])

  const disabled = deployments.filter((d) => !d.enabled)
  const deployedNames = new Set(deployments.map((d) => d.strategy_name))
  const neverDeployed = strategies.filter((s) => !deployedNames.has(s.name))

  async function handleCreate() {
    setCreating(true)
    setCreateError(null)
    try {
      await createDeployment(form)
      setForm({ ...EMPTY_FORM, strategy_name: form.strategy_name })
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : "Failed to create deployment.")
    } finally {
      setCreating(false)
    }
  }

  function deployStrategy(name: string) {
    setForm((f) => ({ ...EMPTY_FORM, strategy_name: name, symbols: f.symbols }))
    formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })
  }

  if (loading) {
    return <p className="text-sm text-[var(--ink-muted)]">Loading…</p>
  }

  return (
    <div className="flex flex-col gap-6">
      {loadError && <p className="text-sm text-[var(--status-critical)]">{loadError}</p>}

      {neverDeployed.length > 0 && (
        <section className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5">
          <h2 className="mb-4 text-sm font-semibold text-[var(--ink-secondary)]">
            Not Yet Deployed
          </h2>
          <div className="flex flex-col gap-2">
            {neverDeployed.map((s) => (
              <div
                key={s.name}
                className="flex items-center justify-between rounded-md border border-[var(--border)] px-4 py-3"
              >
                <div>
                  <span className="font-medium">{s.display_name}</span>
                  <span className="ml-2 rounded-full bg-[var(--surface-2)] px-2 py-0.5 text-xs text-[var(--ink-muted)]">
                    {s.side}
                  </span>
                </div>
                <button
                  onClick={() => deployStrategy(s.name)}
                  className="rounded-md border border-[var(--border)] px-3 py-1 text-xs hover:bg-[var(--surface-2)]"
                >
                  Deploy
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5">
        <h2 className="mb-4 text-sm font-semibold text-[var(--ink-secondary)]">
          Disabled Deployments
        </h2>

        {disabled.length === 0 ? (
          <p className="text-sm text-[var(--ink-muted)]">No disabled deployments.</p>
        ) : (
          <div className="flex flex-col gap-3">
            {disabled.map((d) => (
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

      <section
        ref={formRef}
        className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5"
      >
        <h2 className="mb-1 text-sm font-semibold text-[var(--ink-secondary)]">New Deployment</h2>
        <p className="mb-4 text-xs text-[var(--ink-muted)]">
          Starts running immediately — no restart needed. (A restart is only needed for a
          brand-new strategy file the backend hasn't discovered yet.)
        </p>

        <DeploymentFieldsForm
          form={form}
          setForm={setForm}
          strategies={strategies}
          watchlist={watchlist}
          namedWatchlists={namedWatchlists}
        />

        <button
          onClick={handleCreate}
          disabled={creating || !isDeploymentFormValid(form)}
          className="mt-4 rounded-md bg-[var(--accent)] px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        >
          {creating ? "Deploying…" : "Deploy Strategy"}
        </button>

        {createError && <p className="mt-2 text-xs text-[var(--status-critical)]">{createError}</p>}
      </section>
    </div>
  )
}
