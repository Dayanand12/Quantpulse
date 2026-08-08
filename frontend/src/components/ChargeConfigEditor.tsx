import { useEffect, useState } from "react"
import { api } from "../lib/api"
import type { ChargeConfig } from "../lib/types"

type Status = "loading" | "idle" | "saving" | "saved" | "error"

// UI edits percentages (0.03, 18), not raw fractions (0.0003, 0.18) — this
// is the one place that converts between the two; ChargeConfig itself
// stays a fraction end to end (core/domain/charges.py, /api/settings/charges).
const PCT_FIELDS = [
  { key: "brokerage_pct", label: "Brokerage", hint: "% of order value, per executed order (entry + exit)" },
  { key: "stt_pct", label: "STT", hint: "% of turnover, sell side only" },
  { key: "exchange_txn_pct", label: "Exchange transaction charges", hint: "% of turnover, both legs" },
  { key: "sebi_pct", label: "SEBI charges", hint: "% of turnover, both legs" },
  { key: "stamp_duty_pct", label: "Stamp duty", hint: "% of turnover, buy side only" },
  { key: "gst_pct", label: "GST", hint: "% on (brokerage + exchange transaction charges)" },
] as const

function toPercentForm(config: ChargeConfig): Record<string, string> {
  return {
    brokerage_pct: String(config.brokerage_pct * 100),
    brokerage_max_per_order: String(config.brokerage_max_per_order),
    stt_pct: String(config.stt_pct * 100),
    exchange_txn_pct: String(config.exchange_txn_pct * 100),
    sebi_pct: String(config.sebi_pct * 100),
    stamp_duty_pct: String(config.stamp_duty_pct * 100),
    gst_pct: String(config.gst_pct * 100),
  }
}

function fromPercentForm(form: Record<string, string>): ChargeConfig {
  return {
    brokerage_pct: Number(form.brokerage_pct) / 100,
    brokerage_max_per_order: Number(form.brokerage_max_per_order),
    stt_pct: Number(form.stt_pct) / 100,
    exchange_txn_pct: Number(form.exchange_txn_pct) / 100,
    sebi_pct: Number(form.sebi_pct) / 100,
    stamp_duty_pct: Number(form.stamp_duty_pct) / 100,
    gst_pct: Number(form.gst_pct) / 100,
  }
}

export function ChargeConfigEditor() {
  const [form, setForm] = useState<Record<string, string>>({})
  const [status, setStatus] = useState<Status>("loading")
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .chargeConfig()
      .then((config) => {
        setForm(toPercentForm(config))
        setStatus("idle")
      })
      .catch(() => {
        setError("Failed to load charge settings.")
        setStatus("error")
      })
  }, [])

  function setField(key: string, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }))
    setStatus("idle")
  }

  async function save() {
    setStatus("saving")
    setError(null)
    try {
      const saved = await api.saveChargeConfig(fromPercentForm(form))
      setForm(toPercentForm(saved))
      setStatus("saved")
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save charge settings.")
      setStatus("error")
    }
  }

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5">
      <h2 className="mb-1 text-sm font-semibold text-[var(--ink-secondary)]">
        Brokerage &amp; Taxes
      </h2>
      <p className="mb-4 text-xs text-[var(--ink-muted)]">
        Applied to every trade closed from now on, so realized P&amp;L reflects what actually
        lands in the account. Defaults match Zerodha's intraday equity rates. Past trades keep
        the charges they were closed with — changing these does not retroactively recompute
        history.
      </p>

      {status === "loading" ? (
        <p className="text-sm text-[var(--ink-muted)]">Loading…</p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            {PCT_FIELDS.map(({ key, label, hint }) => (
              <label key={key} className="flex flex-col gap-1">
                <span className="text-xs font-medium text-[var(--ink-secondary)]">{label}</span>
                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    step="any"
                    value={form[key] ?? ""}
                    onChange={(e) => setField(key, e.target.value)}
                    className="w-full rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-2 py-1.5 text-sm outline-none focus:border-[var(--accent)]"
                  />
                  <span className="text-xs text-[var(--ink-muted)]">%</span>
                </div>
                <span className="text-[11px] text-[var(--ink-muted)]">{hint}</span>
              </label>
            ))}

            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium text-[var(--ink-secondary)]">
                Brokerage cap
              </span>
              <div className="flex items-center gap-1">
                <span className="text-xs text-[var(--ink-muted)]">₹</span>
                <input
                  type="number"
                  step="any"
                  value={form.brokerage_max_per_order ?? ""}
                  onChange={(e) => setField("brokerage_max_per_order", e.target.value)}
                  className="w-full rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-2 py-1.5 text-sm outline-none focus:border-[var(--accent)]"
                />
              </div>
              <span className="text-[11px] text-[var(--ink-muted)]">Max brokerage, per executed order</span>
            </label>
          </div>

          <div className="mt-4 flex items-center gap-3">
            <button
              onClick={save}
              disabled={status === "saving"}
              className="rounded-md bg-[var(--accent)] px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              {status === "saving" ? "Saving…" : "Save Charges"}
            </button>
            {status === "saved" && (
              <span className="text-xs text-[var(--status-good)]">Saved.</span>
            )}
            {error && <span className="text-xs text-[var(--status-critical)]">{error}</span>}
          </div>
        </>
      )}
    </div>
  )
}
