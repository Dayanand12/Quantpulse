import { useEffect, useRef, useState } from "react"
import { backtestApi } from "../../lib/backtestApi"
import type { BacktestRunConfig, BatchJobScenario, BatchJobScenarioStatus } from "../../lib/backtestTypes"
import { useBatchJobStore } from "../../store/batchJobStore"

const STATUS_STYLES: Record<BatchJobScenarioStatus, string> = {
  pending: "text-[var(--ink-muted)]",
  running: "text-[var(--accent)]",
  done: "text-[var(--status-good)]",
  skipped: "text-[var(--card-blue)]",
  invalid: "text-[var(--status-critical)]",
  error: "text-[var(--status-critical)]",
}

function scenarioCounts(scenarios: BatchJobScenario[]) {
  const counts = { pending: 0, running: 0, done: 0, skipped: 0, invalid: 0, error: 0 }
  for (const s of scenarios) counts[s.status]++
  return counts
}

interface BulkUploadProps {
  strategy: string
  sharedConfig: BacktestRunConfig
}

// The "prepare every scenario in a spreadsheet, upload once, walk away"
// feature — no panel cap, and the run keeps going server-side even if you
// close the browser (see backtest_server.py's POST /api/backtest/
// batch-jobs and runners/backtesting/batch_job_runner.py). File format
// matches the Analysis tab's "Export Excel" button exactly: a Label
// column plus one column per tuned parameter, so Export -> edit ->
// re-upload is the same file round-tripping.
export function BulkUpload({ strategy, sharedConfig }: BulkUploadProps) {
  const [expanded, setExpanded] = useState(false)
  const [downloadingBlank, setDownloadingBlank] = useState(false)
  const [downloadingFromRuns, setDownloadingFromRuns] = useState(false)
  const [templateError, setTemplateError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const activeJob = useBatchJobStore((s) => s.activeJob)
  const uploading = useBatchJobStore((s) => s.uploading)
  const uploadError = useBatchJobStore((s) => s.uploadError)
  const ensureLoadedForStrategy = useBatchJobStore((s) => s.ensureLoadedForStrategy)
  const upload = useBatchJobStore((s) => s.upload)

  useEffect(() => {
    ensureLoadedForStrategy(strategy)
  }, [strategy, ensureLoadedForStrategy])

  async function downloadBlob(getBlob: () => Promise<Blob>, filename: string) {
    const blob = await getBlob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  async function handleDownloadBlankTemplate() {
    setDownloadingBlank(true)
    setTemplateError(null)
    try {
      await downloadBlob(
        () => backtestApi.downloadBlankTemplate(strategy),
        `${strategy}_scenario_template.xlsx`,
      )
    } catch (e) {
      setTemplateError(e instanceof Error ? e.message : "Failed to build a template.")
    } finally {
      setDownloadingBlank(false)
    }
  }

  async function handleDownloadFromPastRuns() {
    setDownloadingFromRuns(true)
    setTemplateError(null)
    try {
      await downloadBlob(
        () => backtestApi.exportResultsExcel(strategy),
        `${strategy}_backtest_comparison.xlsx`,
      )
    } catch (e) {
      setTemplateError(
        e instanceof Error ? e.message : "No stored runs yet — try \"Download Blank Template\" instead.",
      )
    } finally {
      setDownloadingFromRuns(false)
    }
  }

  async function handleFileChosen(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = "" // allow re-selecting the same file name later
    if (!file) return
    await upload(strategy, sharedConfig, file)
  }

  const counts = activeJob ? scenarioCounts(activeJob.scenarios) : null

  return (
    <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] p-5 backdrop-blur-sm">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center gap-1.5 text-sm font-semibold text-[var(--ink-primary)]"
      >
        <span>{expanded ? "▾" : "▸"}</span>
        Bulk Upload — run every scenario in a spreadsheet
        {activeJob && (activeJob.status === "pending" || activeJob.status === "running") && (
          <span className="ml-1 text-xs font-normal text-[var(--accent)]">
            running… {activeJob.processed_scenarios}/{activeJob.total_scenarios}
          </span>
        )}
      </button>

      {expanded && (
        <div className="mt-4 flex flex-col gap-4">
          <p className="text-xs text-[var(--ink-muted)]">
            Prepare every combination you want tested as rows in an Excel file — a <code>Label</code>{" "}
            column, one column per strategy parameter, and (per row, if you want) its own Timeframe,
            Quantity, Capital, Stop Loss %, Target %, Trailing %, Max Cycles/Day, Start/End Time, Date
            From/Date To, and Charges Enabled — a blank cell in any of those just uses the setting from
            the form above. Give each row its own Date From/Date To (e.g. one row per year) to test the
            same strategy/parameters across separate periods in one upload. Same column shape "Export
            Excel" on the Analysis tab produces, so Export → edit → re-upload works as-is. Upload once
            and this runs in the background against <strong>{strategy || "…"}</strong> — closing this
            tab, or the laptop, doesn't stop it. A bad row (typo'd parameter, invalid timeframe/time/date,
            non-numeric value) is skipped with a reason; every other row still runs. A row identical to
            something you've already tested is recognized as "already tested" and reused instead of
            re-run — so re-uploading an export with a few new rows added only spends time on the new
            ones.
          </p>

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading || !strategy}
              className="rounded-md bg-[var(--accent)] px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              {uploading ? "Uploading…" : "Upload Scenarios (.xlsx)"}
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".xlsx"
              onChange={handleFileChosen}
              className="hidden"
            />
            <button
              type="button"
              onClick={handleDownloadBlankTemplate}
              disabled={downloadingBlank || !strategy}
              title="A blank starting point — one example row with this strategy's default parameter values, ready to duplicate/edit"
              className="rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5 text-xs font-medium hover:bg-[var(--page)] disabled:opacity-50"
            >
              {downloadingBlank ? "Downloading…" : "Download Blank Template"}
            </button>
            <button
              type="button"
              onClick={handleDownloadFromPastRuns}
              disabled={downloadingFromRuns || !strategy}
              title="This strategy's stored runs as a starting point — edit the columns / add rows, then upload it back"
              className="rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5 text-xs font-medium hover:bg-[var(--page)] disabled:opacity-50"
            >
              {downloadingFromRuns ? "Downloading…" : "Download From Past Runs"}
            </button>
          </div>
          {uploadError && <p className="text-xs text-[var(--status-critical)]">{uploadError}</p>}
          {templateError && <p className="text-xs text-[var(--status-critical)]">{templateError}</p>}

          {activeJob && counts && (
            <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-3">
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <span className="font-medium text-[var(--ink-primary)]">
                  Job #{activeJob.id} —{" "}
                  <span
                    className={
                      activeJob.status === "done"
                        ? "text-[var(--status-good)]"
                        : activeJob.status === "failed"
                          ? "text-[var(--status-critical)]"
                          : "text-[var(--accent)]"
                    }
                  >
                    {activeJob.status}
                  </span>
                </span>
                <span className="text-[var(--ink-muted)]">
                  {activeJob.processed_scenarios}/{activeJob.total_scenarios} processed · {counts.done} done
                  {counts.skipped > 0 && ` · ${counts.skipped} already tested`}
                  {counts.invalid > 0 && ` · ${counts.invalid} invalid`}
                  {counts.error > 0 && ` · ${counts.error} error`}
                </span>
              </div>

              {activeJob.error && (
                <p className="mt-2 text-xs text-[var(--status-critical)]">{activeJob.error}</p>
              )}

              <div className="mt-3 max-h-72 overflow-y-auto pr-1">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="text-[var(--ink-muted)]">
                      <th className="pb-1 font-medium">Label</th>
                      <th className="pb-1 font-medium">Parameters</th>
                      <th className="pb-1 font-medium">Risk/Sizing (this row)</th>
                      <th className="pb-1 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {activeJob.scenarios.map((s, i) => (
                      <tr key={i} className="border-t border-[var(--glass-border)]/60">
                        <td className="py-1 pr-2 text-[var(--ink-primary)]">{s.label}</td>
                        <td className="py-1 pr-2 font-mono text-[var(--ink-secondary)]">
                          {Object.entries(s.overrides).map(([k, v]) => `${k}=${v}`).join(", ") || "—"}
                        </td>
                        <td className="py-1 pr-2 font-mono text-[var(--ink-secondary)]">
                          {Object.entries(s.config_overrides).map(([k, v]) => `${k}=${v}`).join(", ") || "—"}
                        </td>
                        <td
                          className={`py-1 ${STATUS_STYLES[s.status]}`}
                          title={
                            s.error ??
                            (s.status === "skipped"
                              ? `Identical to an already-stored result (#${s.saved_result_id}) — not re-run`
                              : undefined)
                          }
                        >
                          {s.status === "skipped" ? "already tested" : s.status}
                          {s.error && <span className="ml-1 text-[10px]">({s.error})</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {!activeJob && (
            <p className="text-xs text-[var(--ink-muted)]">No bulk uploads yet for this strategy.</p>
          )}
        </div>
      )}
    </div>
  )
}
