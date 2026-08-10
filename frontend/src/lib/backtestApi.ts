import type {
  BacktestResultDetail,
  BacktestResultSummary,
  BacktestRunConfig,
  BacktestRunResult,
  BatchJob,
  BatchRunConfig,
  BatchRunResponse,
  StrategyInfo,
} from "./backtestTypes"
import { API_BASE } from "./config"

// Same relative-path-through-the-dev-proxy pattern as lib/api.ts —
// /api/backtest/* routes to the standalone backtest_server.py process
// (see frontend/vite.config.ts), not the main live-trading backend.

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`)
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? `${path} -> ${res.status}`)
  }
  return res.json() as Promise<T>
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? `${path} -> ${res.status}`)
  }
  return res.json() as Promise<T>
}

async function putJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? `${path} -> ${res.status}`)
  }
  return res.json() as Promise<T>
}

async function deleteJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { method: "DELETE" })
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? `${path} -> ${res.status}`)
  }
  return res.json() as Promise<T>
}

async function getBlob(path: string): Promise<Blob> {
  const res = await fetch(`${API_BASE}${path}`)
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? `${path} -> ${res.status}`)
  }
  return res.blob()
}

async function postForm<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { method: "POST", body: form })
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? `${path} -> ${res.status}`)
  }
  return res.json() as Promise<T>
}

export const backtestApi = {
  strategies: () => getJSON<StrategyInfo[]>("/api/backtest/strategies"),
  watchlist: () => getJSON<{ symbols: string[] }>("/api/backtest/watchlist"),
  run: (config: BacktestRunConfig) => postJSON<BacktestRunResult>("/api/backtest/run", config),
  // The "6 panels" feature — same strategy, up to 6 parameter-override
  // sets, run in one request (parallelized server-side). `config.panels`
  // can be a subset (e.g. one panel) for a single panel's own Run button,
  // or the full set for "Run All" — same endpoint either way.
  runBatch: (config: BatchRunConfig) => postJSON<BatchRunResponse>("/api/backtest/run-batch", config),
  cloneStrategy: (baseStrategy: string, newName: string) =>
    postJSON<StrategyInfo>("/api/backtest/strategies/clone", {
      base_strategy: baseStrategy,
      new_name: newName,
    }),
  // The Analysis tab's data source — every backtest run ever logged for a
  // strategy (see backtest_server.py's auto-save on /api/backtest/run),
  // deduplicated by parameters so re-running the same config never shows
  // up twice.
  results: (strategy: string) =>
    getJSON<BacktestResultSummary[]>(`/api/backtest/results?strategy=${encodeURIComponent(strategy)}`),
  resultDetail: (id: number) => getJSON<BacktestResultDetail>(`/api/backtest/results/${id}`),
  // Every stored run for a strategy as one .xlsx — same data as the
  // Parameter Comparison chart, for a spreadsheet or pasting/uploading
  // into an LLM for tuning research all at once.
  exportResultsExcel: (strategy: string) =>
    getBlob(`/api/backtest/results/export?strategy=${encodeURIComponent(strategy)}`),
  // Bulk upload: an Excel of parameter scenarios, processed in the
  // background — `form` carries the strategy, shared run settings, and
  // the file itself (multipart, not JSON). Returns immediately once
  // parsing/validation finishes, well before any backtest has run.
  uploadBatchJob: (form: FormData) => postForm<BatchJob>("/api/backtest/batch-jobs", form),
  getBatchJob: (id: number) => getJSON<BatchJob>(`/api/backtest/batch-jobs/${id}`),
  listBatchJobs: (strategy: string) =>
    getJSON<BatchJob[]>(`/api/backtest/batch-jobs?strategy=${encodeURIComponent(strategy)}`),
  // A blank starter workbook for a strategy with no stored runs yet — one
  // example row: the shared risk/sizing defaults + this strategy's actual
  // conditions.json parameter values, ready to duplicate/edit rows from.
  downloadBlankTemplate: (strategy: string) =>
    getBlob(`/api/backtest/batch-jobs/template?strategy=${encodeURIComponent(strategy)}`),
  // The strategy's conditions.json (core/domain/strategy_conditions.py) —
  // indicator thresholds/conditions, editable here instead of in code.
  // has_params is false for a strategy not yet migrated off hand-written
  // screen() logic (e.g. orb_reversal).
  strategyParams: (name: string) =>
    getJSON<{ has_params: boolean; raw_json: string | null }>(
      `/api/backtest/strategies/${encodeURIComponent(name)}/params`,
    ),
  saveStrategyParams: (name: string, rawJson: string) =>
    putJSON<{ raw_json: string }>(`/api/backtest/strategies/${encodeURIComponent(name)}/params`, {
      raw_json: rawJson,
    }),
  // Rejected with a clear error (not silently ignored) if the strategy is
  // currently referenced by any deployment — see backtest_server.py's
  // safety check.
  deleteStrategy: (name: string) =>
    deleteJSON<{ deleted: string }>(`/api/backtest/strategies/${encodeURIComponent(name)}`),
  deleteResult: (id: number) => deleteJSON<{ deleted: number }>(`/api/backtest/results/${id}`),
}
