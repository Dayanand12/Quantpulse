# QuantPulse — Implemented Features Checklist

Snapshot of what's actually built and working in the codebase as of 2026-07-28.
Check items off as you validate them; the "Known gaps" section at the bottom lists
what's explicitly *not* done yet, so it isn't accidentally checked off too.

## 1. Live Market Data

- [ ] Zerodha KiteConnect integration — auth/session, WebSocket ticker (`Data_ingestion/`, `infrastructure/trading/market_data/zerodha_provider.py`)
- [ ] Live tick ingestion for every watchlist symbol, including indices (NIFTY 50, NIFTY BANK, INDIA VIX)
- [ ] Candle building + indicator pipeline (EMA5/9/21, RSI, ADX, ATR%, VWAP, volume ratio, ORB low/distance) — `live/live_engine.py`
- [ ] Live market ticker bar on the dashboard (raw LTP + day change, works even for symbols with no indicator snapshot yet)

## 2. Strategy Engine

- [ ] Pluggable strategy interface (`IStrategy`: `name`, `display_name`, `side`, `screen()`) — `core/application/interfaces/strategy.py`
- [ ] Auto-discovery of strategies dropped into `strategies/*.py` — no registration step, restart picks them up (`infrastructure/strategies/file_strategy_registry.py`)
- [ ] Universal risk/sizing model shared by every strategy — quantity, stop-loss %, target %, trailing %, max cycles/day (`core.domain.models.StrategyConfig`)
- [ ] BUY-side and SELL-side entry/exit math both supported (`live/execution_manager.py`)
- [ ] Sample strategies included: ORB Reversal (short), EMA 5/9 Crossover (long), template `my_strategy`, plus `TEST: Always Long` / `TEST: Always Short` for exercising the pipeline on demand
- [ ] In-browser Strategy Builder (CodeMirror editor, create/edit/save strategy source files via API) — Strategy Builder page

## 3. Deployments (Multi-Strategy Execution)

- [ ] Multiple independent deployments running concurrently, each with its own strategy, symbol subset, capital pool, and risk config (`core/container.py::DeploymentRuntime`)
- [ ] Deployments persisted to SQLite (create/update/delete via API and Strategies page)
- [ ] Per-deployment `ExecutionManager` loop: screens candidates, manages entries (skips symbols already in position, respects max cycles/day), manages exits (SL / target / trailing stop)
- [ ] Watchlist management (persisted, editable from Settings page, seeds from `stocks.json` on first run)

## 4. Paper Trading

- [ ] Simulated broker per deployment (`live/paper_broker.py`) — capital tracking, position entry/exit, realized P&L
- [ ] Open positions view with live unrealized P&L (Positions page, Live Dashboard)
- [ ] Trade log with entry/exit/side/qty/P&L per trade (Trades page, Live Dashboard)
- [ ] Equity curve chart from trade history

## 5. Performance Metrics

- [ ] Per-strategy metrics: total trades, win rate, profit factor, gross profit/loss, total P&L, max drawdown (₹ and %), avg R-multiple, Sharpe ratio (`core/domain/metrics.py`) — Performance page
- [ ] Metrics computed identically for every strategy (nothing hardcoded to one strategy)

## 6. Persistence (Database)

- [ ] SQLite + SQLAlchemy + Alembic, migrations run automatically at startup
- [ ] Watchlist and deployments persisted and survive restarts
- [ ] **Trade history now persisted too** — every closed trade (with deployment/strategy tag, entry/exit, P&L, initial stop-loss, real close timestamp) is written to the `trades` table via an event-bus subscriber (`infrastructure/persistence/sql_trade_journal.py`), so history survives a backend restart

## 7. Reporting

- [ ] On-demand Market Analysis report (regime/trend/volatility/decision snapshot for one symbol, written to a `.txt` file) — Market Analysis page
- [ ] **End-of-day trades + strategy metrics report** — Excel workbook (`Trades` sheet + `Strategy Metrics` sheet), generated automatically once a day at a configured time (default 3:35 PM) and also available on demand for any date via `GET /api/eod-report?date=YYYY-MM-DD`

## 8. Frontend (React + Vite)

- [ ] Pages: Live Dashboard, Positions, Trades, Performance, Screener, Market Analysis, Strategies, Strategy Builder, Settings
- [ ] Real-time updates over WebSocket (`/ws/live`) — snapshot, stage results, broker status, positions, market ticker, pushed every second
- [ ] Live ORB Screener funnel (Stage 1 / 2 / 3 candidate counts, sortable full snapshot table)
- [ ] Connection status indicator

## 9. Dev Tooling

- [ ] Single-command dev launcher (`python run_dev.py`) — starts backend + frontend together instead of two terminals
- [ ] Structured logging (`infrastructure/logging/logger.py`)
- [ ] Centralized settings via environment variables / `.env` (`infrastructure/config/settings.py`)

---

## Known gaps (explicitly NOT done yet — don't check these off)

- Trade entry time isn't recorded (only exit/close time) — only half the trade lifecycle has a real timestamp.
- No authentication beyond a single hardcoded user (`infrastructure/auth/single_user_provider.py`).
- Paper trading capital isn't editable from the UI (Settings page says so directly).
- The standalone `BackTesting/` and `backtest/` folders are older, separate modules — not wired into the live strategy/deployment system above; running a backtest today means running those scripts directly, not through the UI.
- No real (non-paper) broker order placement — everything today is simulated.
- No automated test coverage beyond `tests/unit/test_metrics.py`.
