import { create } from "zustand"
import { backtestApi } from "../lib/backtestApi"
import type { BacktestRunConfig, BatchJob } from "../lib/backtestTypes"
import { playBacktestCompleteSound } from "../lib/notifySound"

// The bulk-upload feature's state. Module-level Zustand store (same
// pattern as liveStore.ts/batchRunnerStore.ts) rather than component
// state — the whole point of a background job is that it keeps running
// after you navigate away or close the browser; polling for its status
// needs to survive exactly the same way, not reset every time you
// revisit the Backtest page.
const POLL_INTERVAL_MS = 3000

interface BatchJobState {
  strategy: string
  activeJob: BatchJob | null
  uploading: boolean
  uploadError: string | null
  ensureLoadedForStrategy: (strategy: string) => void
  upload: (strategy: string, sharedConfig: BacktestRunConfig, file: File) => Promise<void>
}

// Module-scope, not store state — a setInterval handle isn't serializable
// UI state, it's a side-channel resource, same reasoning as liveStore.ts's
// module-level `socket`.
let pollTimer: ReturnType<typeof setInterval> | null = null

function stopPolling() {
  if (pollTimer !== null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function startPolling(
  get: () => BatchJobState,
  set: (partial: Partial<BatchJobState>) => void,
  jobId: number,
  strategy: string,
) {
  stopPolling()
  pollTimer = setInterval(async () => {
    try {
      const job = await backtestApi.getBatchJob(jobId)
      // The store may have moved on to a different strategy/job since
      // this tick was scheduled — don't let a stale poll overwrite it.
      if (get().strategy !== strategy || get().activeJob?.id !== jobId) {
        stopPolling()
        return
      }
      set({ activeJob: job })
      if (job.status === "done" || job.status === "failed") {
        stopPolling()
        playBacktestCompleteSound()
      }
    } catch {
      stopPolling()
    }
  }, POLL_INTERVAL_MS)
}

export const useBatchJobStore = create<BatchJobState>((set, get) => ({
  strategy: "",
  activeJob: null,
  uploading: false,
  uploadError: null,

  ensureLoadedForStrategy: (strategy) => {
    if (!strategy || get().strategy === strategy) return

    stopPolling()
    set({ strategy, activeJob: null, uploadError: null })

    backtestApi
      .listBatchJobs(strategy)
      .then((jobs) => {
        if (get().strategy !== strategy) return // switched again before this landed
        const latest = jobs[0] ?? null
        set({ activeJob: latest })
        if (latest && (latest.status === "pending" || latest.status === "running")) {
          startPolling(get, set, latest.id, strategy)
        }
      })
      .catch(() => {
        /* no jobs yet for this strategy, or backend unreachable — leave activeJob null */
      })
  },

  upload: async (strategy, sharedConfig, file) => {
    set({ uploading: true, uploadError: null })
    try {
      const form = new FormData()
      form.append("strategy", strategy)
      if (sharedConfig.symbols && sharedConfig.symbols.length > 0) {
        form.append("symbols", sharedConfig.symbols.join(","))
      }
      form.append("timeframe", sharedConfig.timeframe)
      form.append("quantity", String(sharedConfig.quantity))
      form.append("stoploss_pct", String(sharedConfig.stoploss_pct))
      form.append("target_pct", String(sharedConfig.target_pct))
      form.append("trailing_pct", String(sharedConfig.trailing_pct))
      form.append("max_cycles_per_day", String(sharedConfig.max_cycles_per_day))
      form.append("start_time", sharedConfig.start_time)
      form.append("end_time", sharedConfig.end_time)
      form.append("capital", String(sharedConfig.capital))
      form.append("charges", String(sharedConfig.charges))
      if (sharedConfig.date_from) form.append("date_from", sharedConfig.date_from)
      if (sharedConfig.date_to) form.append("date_to", sharedConfig.date_to)
      form.append("file", file)

      const job = await backtestApi.uploadBatchJob(form)
      set({ activeJob: job, uploading: false })
      startPolling(get, set, job.id, strategy)
    } catch (e) {
      set({ uploadError: e instanceof Error ? e.message : "Upload failed.", uploading: false })
    }
  },
}))
