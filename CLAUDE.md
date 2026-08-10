# QuantPulse

A personal algorithmic-trading research tool: live paper trading against real
Zerodha market data, plus a separate backtesting system for tuning strategies
against historical data. **Paper trading only** — no code path anywhere sends
a real order to the broker.

Backend: Python (FastAPI), hexagonal/clean architecture. Frontend: React +
TypeScript + Vite + Tailwind, in `frontend/`.

## Running it

Two independent backends, each on its own port, sharing one frontend dev
server via Vite's proxy (`frontend/vite.config.ts`):

- **`python run_live.py`** (or `python run_dev.py` to also launch the
  frontend) — live paper-trading backend, port 5000. Needs a working Zerodha
  session.
- **`python run_backtest_server.py`** — standalone backtest API, port 5050.
  No Zerodha session needed; reads historical CSVs + the watchlist DB table
  only. This is what the Backtest/Analysis pages and the Telegram bot talk to.
- **`python run_all.py`** — starts both backends + one shared frontend dev
  server together. Use this for a normal working session.
- **`python run_backtest_ui.py`** — backtest API + frontend only, opens the
  browser straight to `/backtest`. Use when you don't need live trading up.

Frontend alone: `cd frontend && npm run dev` (port 5173, proxies
`/api/backtest/*` to 5050 and everything else to 5000).

Tests: `python -m pytest tests/ -q` from the repo root (currently 450+
passing). Run this after any backend change before calling it done.

### Windows-specific gotcha

Starting `python run_backtest_server.py` from a shell shows up as **two**
`python.exe` processes (a venv-launcher stub parent + the real interpreter
child) — that's normal Windows venv behavior here, not two competing
instances. Before assuming something's duplicated, check
`netstat -ano | grep :5050` for which PID is actually LISTENING.

## Architecture

Hexagonal/clean architecture — domain logic doesn't import infrastructure.

- **`core/domain/`** — pure domain models and logic: `models.py` (Trade,
  StrategyConfig, Deployment), `metrics.py` (PerformanceMetrics), `charges.py`
  (Zerodha fee model), `strategy_conditions.py` (the JSON condition
  evaluator), `batch_job.py`, `backtest_result.py`.
- **`core/application/interfaces/`** — ports (ABCs): repositories, the
  strategy registry, the market data provider, etc. Infrastructure implements
  these; domain/application code depends only on the interface.
- **`infrastructure/`** — adapters: `persistence/` (SQLAlchemy models +
  repos + Alembic migrations, SQLite with WAL mode), `strategies/`
  (filesystem-backed strategy source/params repos), `trading/`, `auth/`.
- **`runners/backtesting/`** — the backtest engine (`engine.py`), historical
  CSV loading, the batch-job pipeline (see below), Excel report generation
  (`report.py`).
- **`runners/paper_trading/`** — the live engine, execution manager, paper
  broker.
- **`strategies/`** — one file per strategy. Most are `JsonConditionStrategy`
  subclasses (see below); a few (e.g. `orb_reversal`) still use hand-written
  `screen()` logic.
- **`services/`** — cross-cutting background jobs: EOD reports, DB backups,
  the market analysis engine.
- **`server/main.py`** — the live app's FastAPI wiring. **`backtest_server.py`**
  (repo root) — the standalone backtest API's wiring, separate app.

## The strategy system

A strategy is a small class (`name`, `display_name`, `side`, `screen()`).
Two shapes:

1. **`JsonConditionStrategy`** subclasses (`core/domain/
   json_condition_strategy.py`) — the class itself is ~4 lines; the actual
   entry logic lives in a sibling `strategies/<name>.json` (a `parameters`
   block + a `conditions` list, evaluated by `core/domain/
   strategy_conditions.py`). This is how most strategies work now. Editing
   the JSON changes behavior with no code change.
2. Hand-written `screen()` — older strategies, or ones needing logic the
   JSON condition language can't express (staged funnels, etc.).

`runners/backtesting/strategy_resolver.py` resolves a name to a class via
normal `import strategies.<name>`; `infrastructure/strategies/
file_strategy_registry.py` does the same dynamically for the live app.

## Backtesting: single runs, "6 panels", and bulk batch jobs

Three ways to run a backtest, all converging on the same engine
(`runners/backtesting/engine.py::run_backtest`):

1. **Single run** — the Backtest page's form, or `run_backtest.py` (CLI).
2. **"6 panels"** (`runners/backtesting/batch_runner.py`, `POST /api/
   backtest/run-batch`) — synchronous, capped at 6, for "try a few variants
   right now."
3. **Batch jobs** (`runners/backtesting/batch_job_runner.py` +
   `batch_job_import.py`, `POST /api/backtest/batch-jobs`) — upload an Excel
   of scenarios (one row each), processed in the background on its own
   thread, detached from the HTTP request — closing the browser doesn't stop
   it. Every risk/sizing field (timeframe, SL/TP/trailing, quantity, capital,
   date range, ...) is **per-row overridable**; a blank cell falls back to
   the job's shared settings. A row identical to an already-stored result is
   marked `skipped` instead of recomputed (`_find_already_tested`, keyed off
   `core/domain/backtest_result.py::BacktestRunParams` — the same identity
   `save_backtest_result` dedups on). Same pipeline is reachable from the
   **Telegram bot** (`runners/backtesting/telegram_bot.py`) — send a file,
   get results back, no browser needed. Commands: `/strategies`,
   `template <name>`, `results <name>`, `status <name>`.

Every stored `backtest_results` row is deduped on that same
`BacktestRunParams` identity (strategy, symbols, dates, risk settings,
resolved `conditions.json` parameters) — re-running identical inputs updates
the row in place, never creates a duplicate.

`runners/backtesting/report.py` builds the Excel exports (comparison report,
blank scenario template) — columns are color-coded (input/output/identifier)
and a separate "Column Guide" sheet documents the split, so the file is
self-explanatory to a human or an LLM without extra prompting. That guide
sheet is *always* the second sheet — the first sheet's shape must stay
exactly what `batch_job_import.py::parse_scenarios_from_excel` expects,
since Export → edit → re-upload is a supported round trip.

## Conventions and lessons learned the hard way

- **Check for a running batch job before restarting `backtest_server.py`.**
  Force-killing the process mid-job orphans it at `status="running"`
  forever — nothing will ever finish it. `GET /api/backtest/batch-jobs?
  strategy=X` for each strategy, or just ask "is anything running" first.
- **Telegram bot restarts need a ~10s gap.** Killing and immediately
  restarting the poller causes `getUpdates` to 409-conflict with the
  previous connection Telegram's servers haven't released yet. Wait, then
  restart, then verify the log shows no `409` for ~20-30s before declaring
  it healthy.
- **Frontend state that should survive page navigation belongs in a Zustand
  store, not local `useState`.** React Router unmounts the whole page
  component tree on navigation — local state (including a strategy
  selection, or a batch job's in-progress panel) resets to defaults and
  looks like data loss even though the backend job is still running fine.
  See `frontend/src/store/` for the existing pattern (`liveStore.ts`,
  `batchJobStore.ts`, `batchRunnerStore.ts`, `backtestPageStore.ts`).
- **Look-ahead bias**: any field derived from an in-progress period (e.g.
  the opening-range high/low before 9:30) must be masked to `None` until
  that period actually closes, in both the backtest snapshot builder and the
  live engine, or a backtest will silently cheat.
- **CLI vs API result-shape parity matters.** `run_backtest.py` and
  `backtest_server.py` must save byte-identical result JSON shapes to
  `backtest_results`, or the Analysis tab crashes on the CLI-saved rows.
  Shared helpers in `runners/backtesting/result_persistence.py` exist
  specifically to prevent this drifting apart again.
- **Real Excel cells aren't always the string you'd expect.** Typing a time
  or date into a cell auto-formats it as a native Excel value; pandas hands
  back a `datetime.time`/`datetime.datetime`/`pd.Timestamp` object, not the
  string `"09:20"`. `batch_job_import.py`'s parsers handle both forms —
  don't regress that if touching them.
- **Validate against real data, not just unit tests.** This codebase's
  history is full of bugs that only surfaced when checked against actual
  historical CSVs or a live API call — trade counts changing when they
  shouldn't, a stored result missing a field the UI expected, a metric
  computed from leaked future data. Prefer running the real thing over
  trusting that a mock/unit test alone proves correctness.

## Database

SQLite (`infrastructure/persistence/database.py`, WAL mode), migrated with
Alembic (`infrastructure/persistence/alembic/`, run via `python -m alembic
upgrade head`). Every repository method opens its own session per call —
safe to call from a background thread (batch jobs, the Telegram poller) that
isn't the request thread that started it.

Per-strategy row counts of a few thousand are fast (indexed on
`strategy_name`); total row count across all strategies barely matters since
every real query filters by strategy first.
