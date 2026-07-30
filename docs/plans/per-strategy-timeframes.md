# Per-Strategy Timeframe Selection

**Status:** Implemented (2026-07-30), same session this plan was written in. All sections below describe what was actually built — no deviations from the plan except one addition: warm-start's per-candle multi-timeframe resampling turned out to be O(n²) and made a 3,000-candle backfill take minutes instead of seconds (see the note at the end of this doc). Fixed by separating cheap per-candle ingestion from the expensive resample-and-recompute step, which now runs once per symbol after the full historical batch is ingested, not once per candle.

## Context

Every strategy today runs on the same, hardcoded 1-minute candle series. `live/candle_builder.py` buckets every live tick into 1-minute OHLC candles, and `live/live_engine.py::LiveEngine` computes one set of indicators (EMA5/9/21, RSI14, ADX14, ATR%, VWAP, volume ratio, opening-range distance) per symbol, off that single 1-minute series. Every deployment watching a symbol — regardless of strategy — reads that same snapshot.

The user wants to pick a timeframe (1m / 5m / 15m / etc.) per **deployment**, so a fast ORB-style strategy and a slower trend strategy can each get indicators computed on the bar size that actually suits them, instead of everything being forced onto 1-minute bars.

This document is a plan only. It assumes the reader has no memory of any prior conversation.

---

## Approach

**Core idea: keep a single 1-minute base candle series per symbol (unchanged), and derive every other timeframe by resampling groups of consecutive 1-minute candles on every new candle close.** Indicators get computed once per `(symbol, timeframe)` pair that's actually supported, not once per deployment.

### Why resampling from a 1-minute base, not fetching each timeframe natively

Kite's historical API does support native interval strings (`"3minute"`, `"5minute"`, `"15minute"`, etc.), and it would be possible to fetch and stream each timeframe independently. This plan rejects that in favor of resampling, because:

- **Live ticks only arrive once, at tick resolution.** Kite's WebSocket delivers raw ticks, not multi-resolution candles. Supporting N timeframes natively would mean N parallel `CandleBuilder` instances live, each independently bucketing the same tick stream — multiplying the live-path complexity by the number of supported timeframes.
- **Warm-start (added earlier this session, see Dependencies below) would need N separate historical API calls per symbol** instead of one, adding rate-limit pressure for no real benefit.
- **Resampling from one 1-minute base guarantees perfect internal consistency** — a 15-minute bar is *always* exactly 15 of the same 1-minute bars combined. Two independently-fetched series (1-min from one API call, 15-min from another) could disagree at the edges due to how each interval's boundary/session handling works on Kite's side.

### Why timeframe is a per-deployment field, not a per-strategy fixed attribute

The user's own framing was "provision to select timeframe" — i.e. chosen at deploy time, not hardcoded into the strategy file. This also means the *same* strategy can be deployed twice at different timeframes for comparison (e.g. EMA Crossover at 5m vs 15m) at zero extra architectural cost — it's just another `StrategyConfig` field, the same way `quantity`, `stoploss_pct`, and (from earlier this session) `start_time`/`end_time` already work. `IStrategy.screen()` itself needs no interface change: RSI/EMA/ADX values are timeframe-agnostic from the strategy's point of view, it just receives whatever bar size its deployment is configured for.

### Why an eager fixed set of timeframes, not dynamic per-deployment tracking

`LiveEngine` will always compute a fixed, small set of supported timeframes (proposed: 1, 3, 5, 10, 15, 30, 60 minutes) for every symbol, regardless of whether a deployment currently uses each one — rather than dynamically tracking "which timeframes does at least one live deployment need right now." Resampling + talib on a few hundred rows is fast (polars is columnar/vectorized); doing it for 7 timeframes × ~5 symbols once a minute is trivial. Dynamic tracking would save a small amount of CPU at the cost of real complexity (registering/deregistering timeframes as deployments change, deciding what happens to a timeframe's data if the last deployment using it is deleted). Not worth it unless profiling ever shows otherwise.

### Why recompute happens on every 1-minute candle close, not on each higher-timeframe boundary

When a new 1-minute candle closes, every active timeframe's *current, still-forming* bucket gets recomputed (e.g. at minute 3 of a 5-minute bucket, the 5-minute indicators reflect 3 minutes of data so far). This matches how a live trading chart behaves — the current candle updates continuously — and matches the existing 1-minute behavior (which already recomputes on every close, since 1-minute *is* the base granularity, so there's no existing notion of "wait for the bar to fully close" to preserve). The alternative (only recompute a timeframe's indicators when a full bar of that size has elapsed) would make higher timeframes feel "stale" for most of each bar and was rejected.

### What actually changes in `LiveEngine`

Today:
```python
self.data = {symbol: <1-min OHLCV DataFrame>}
self.indicator_snapshot = {}   # symbol -> {ltp, ema5, ..., orb_low, distance_to_or_low}
```

Proposed:
```python
self.data = {symbol: <1-min OHLCV DataFrame>}     # UNCHANGED — still the single source of truth
self.indicator_snapshot = {}   # symbol -> {timeframe -> {ltp, ema5, ..., orb_low, distance_to_or_low}}
```

`on_new_candle(symbol, candle)`:
1. Append the new 1-minute candle to `self.data[symbol]` — **unchanged**.
2. Update opening-range tracking (`self.or_data`) — **unchanged**; OR is wall-clock-anchored (9:15–9:30 IST) regardless of what timeframe a strategy reads, so it doesn't need to become timeframe-aware.
3. **New:** for each supported timeframe, resample `self.data[symbol]` (via polars `group_by_dynamic`, wall-clock-aligned buckets — see Risks) into that timeframe's OHLCV, then run the *exact same* indicator block that exists today (EMA5/9/21, RSI14, ADX14, ATR%, VWAP, volume ratio, `orb_low`/`distance_to_or_low` off `self.or_data`) against the resampled frame, writing the result into `self.indicator_snapshot[symbol][timeframe]`.

`get_snapshot(timeframe="minute")` (new optional parameter, default preserves today's behavior exactly): returns `self.indicator_snapshot.get(timeframe, {})` — same flat `symbol -> dict` shape callers get today when they don't pass an argument.

`warm_start(symbol, historical_candles)` needs **no changes** — it already just calls `on_new_candle` once per historical candle. Once `on_new_candle` is multi-timeframe-aware internally, warm-start automatically warms every timeframe, not just 1-minute, for free.

### What changes above `LiveEngine`

- `live/execution_manager.py::ExecutionManager` gains a `timeframe` constructor parameter (default `"minute"`, so existing call sites/tests keep working). `evaluate()` changes from `self.live_engine.get_snapshot()` to `self.live_engine.get_snapshot(self.timeframe)`. Nothing else in `ExecutionManager` changes — `_manage_entries`/`_manage_exits` just consume whatever snapshot dict they're handed, same as today.
- `core/container.py::build_container` passes `deployment.config.timeframe` into `ExecutionManager(...)`.
- `core/domain/models.py::StrategyConfig` gains `timeframe: str = "minute"` (same string vocabulary Kite's own API uses for the base 1-minute interval, for familiarity — but see the note below, this is *not* passed to Kite directly).
- The API/display path (`infrastructure/trading/live_engine_adapter.py::LiveEngineAdapter.get_snapshot()`, used by the Screener page, Live Dashboard, and Market Analysis via `ITradingEngine`) is **not changed** — it keeps calling `live_engine.get_snapshot()` with no argument, so it keeps getting the 1-minute view. Those pages continue showing the base timeframe regardless of what any individual deployment is configured for. Giving the *display* pages their own timeframe selector is a natural future extension but is explicitly out of scope here — the user's request was about strategy execution, not the Screener/Market Analysis UI.

**Important naming distinction to preserve:** `deployment.config.timeframe` (this plan's new field, used only for internal resampling) is a *different concept* from the `interval="minute"` parameter `live/warm_start.py` passes to `ZerodhaClient.fetch_historical_data()`. Warm-start's fetch stays hardcoded to 1-minute — it always fetches the finest base data, exactly as today. The per-deployment `timeframe` never gets passed to Kite; it only controls which resampled view of the already-fetched 1-minute data a given deployment reads.

---

## Migration

New Alembic migration, following the exact pattern of `infrastructure/persistence/alembic/versions/5f678bcbcdfa_add_active_window_to_deployments.py` (added earlier this session, for `start_time`/`end_time`):

```python
op.add_column(
    'deployments',
    sa.Column('timeframe', sa.String(length=10), nullable=False, server_default='minute'),
)
```

- Every existing deployment gets backfilled to `'minute'` — the exact behavior every deployment already has today, so nothing changes for any current deployment on upgrade.
- Purely additive column; no data loss risk.
- This is a local, single-instance SQLite app — there's no "downtime" concept to manage. The real equivalent is restart-to-apply: like every other deployment-config field added this session (capital, quantity, active window), changing a deployment's timeframe takes effect only after the backend restarts and `build_container()` re-reads the deployment table. This is consistent with existing behavior, not a new limitation introduced by this change.

---

## Affected files

Everything that reads or writes `LiveEngine`'s snapshot, `StrategyConfig`, or the `deployments` table — not just the files being edited.

**Core engine (edited):**
- `live/live_engine.py` — `indicator_snapshot` becomes nested by timeframe; `get_snapshot(timeframe=...)`; `on_new_candle` internals loop over supported timeframes. This is the highest-risk file in the change.
- `live/warm_start.py` — likely edited only to increase `_LOOKBACK_DAYS` (currently 5) if higher timeframes are supported — see Risks. `warm_start_indicators()` itself and `LiveEngine.warm_start()` need no logic changes.
- `live/execution_manager.py` — `timeframe` constructor param; one-line change in `evaluate()`.

**Read-only, confirmed unaffected (worth listing so this isn't re-litigated next session):**
- `live/candle_builder.py` — stays the 1-minute tick-bucketing base layer, untouched.
- `live/deployment_runner.py` — only calls `execution_manager.evaluate()` and checks the active-window; timeframe is orthogonal to it.
- `backend/filter_engine.py` — `stage1_filter`/`stage2_filter`/`stage3_filter` just read dict keys off whatever snapshot they're given; already timeframe-agnostic.
- `backtest/indicators.py::IndicatorCalculator` — generic talib wrappers over any OHLCV DataFrame; reused as-is for every resampled timeframe, no changes needed.
- `backend/market_analysis_engine.py` — separate on-demand REST-fetch code path, unrelated to `LiveEngine`'s live snapshot; out of scope.
- `infrastructure/trading/live_engine_adapter.py` — keeps calling `get_snapshot()` with no args; the new default parameter means zero code change here, only worth confirming with a test.

**Persistence (edited):**
- `infrastructure/persistence/models.py::DeploymentRecord` — new `timeframe` column.
- `infrastructure/persistence/sql_deployment_repository.py` — map `timeframe` in both `_to_domain()` and `save_deployment()` (same two spots `start_time`/`end_time` were added).
- New Alembic migration file (see above).

**API (edited):**
- `server/main.py` — `DeploymentRequest` gains `timeframe: str = "minute"` with validation against the supported set (mirror the `HHMM_PATTERN` regex-validation approach already used for `start_time`/`end_time`); `_deployment_to_dict` includes it; both `create_deployment`/`update_deployment` pass it into `StrategyConfig(...)`.

**Frontend (edited):**
- `frontend/src/lib/types.ts` — `Deployment`/`DeploymentInput` gain `timeframe: string`.
- `frontend/src/components/DeploymentFieldsForm.tsx` — new dropdown field (Timeframe: 1m/3m/5m/10m/15m/30m/60m), same field-rendering conventions as the existing number/time fields in that component.
- `frontend/src/pages/Strategies.tsx` — `EMPTY_FORM` default, `toDeploymentInput()` mapper, and a small display badge (e.g. "5min") next to the existing "Active HH:MM–HH:MM" badge added earlier this session, for the same reason — so the setting is visible at a glance, not just in the edit form.

**Tests — everything that constructs `LiveEngine`, calls `get_snapshot()`, constructs `ExecutionManager`, or round-trips `StrategyConfig`/`Deployment`:**
- `tests/unit/test_live_engine_warm_start.py` — existing tests must keep passing unchanged (default-timeframe backward compatibility is a design goal, not just a nice-to-have); add new tests for resampling correctness (see Risks — this is the highest-value new test surface).
- `tests/unit/test_execution_manager.py` — existing constructor calls (no `timeframe` arg) must keep working via the default; add a test confirming `evaluate()` requests the configured timeframe.
- `tests/unit/test_warm_start.py` — should be unaffected (orchestration-level, doesn't know about timeframes) — confirm with a run, don't assume.
- `tests/unit/test_sql_deployment_repository.py` — extend for `timeframe` round-trip and default, mirroring the `start_time`/`end_time` tests added this session.
- `tests/integration/test_api.py` — extend `make_deployment_payload()` default + add validation tests (rejects unsupported timeframe string, accepts each supported value).
- `tests/unit/test_deployment_runner.py` — confirm unaffected (timeframe is orthogonal to the active-window check).
- `tests/unit/test_metrics.py` and analytics tests — confirm unaffected (trades/metrics never touch timeframe).

---

## Edge cases and risks

1. **Higher timeframes need proportionally more warm-up history.** The existing "need 25 bars before indicators appear" rule (`live/live_engine.py`, `if df.height < 25: return`) means a 60-minute timeframe needs 25×60 = 1500 minutes ≈ 4 trading days of 1-minute data before it produces a value. `live/warm_start.py`'s current `_LOOKBACK_DAYS = 5` is only just enough for that, and was tuned this session with only 1-minute in mind. **Action needed:** either bump `_LOOKBACK_DAYS` (e.g. to 10, matching `backend/market_analysis_engine.py`'s own lookback) if 60-minute is going to be a real supported option, or deliberately cap the dropdown at a more conservative maximum (e.g. 30 minutes) to keep warm-up comfortably fast. This is a real decision to make during implementation, not something this plan resolves.

2. **Resampling bucket alignment must match wall-clock expectations.** A "5-minute candle" needs to mean 09:15–09:20, 09:20–09:25, etc. — the same boundaries a trader sees on Zerodha's own chart — not an arbitrary offset from whenever the first tick happened to arrive. This needs to be verified empirically against the polars version in use (`group_by_dynamic`'s bucketing behavior) with a dedicated unit test asserting a known synthetic 1-minute series resamples into exactly the expected 5-minute boundaries. This is the single highest-risk piece of new logic in the whole change — get it wrong and every higher-timeframe indicator silently disagrees with what the user sees on their broker's chart, which is exactly the kind of mismatch this session spent real effort verifying *against* for the 1-minute case.

3. **The last (currently-forming) bucket of a resampled timeframe is partial by design** — see "Approach" above for why this is the intended behavior, not a bug. Worth a code comment at the point of resampling so a future reader doesn't "fix" it.

4. **Indices (NIFTY 50, NIFTY BANK, INDIA VIX) still never get an indicator snapshot at any timeframe.** The existing zero-volume gate in `on_new_candle` (`if total_volume == 0: return`) is orthogonal to this change — it will keep applying identically inside the new per-timeframe loop. Not something this plan needs to fix, just something not to be surprised by.

5. **A coarse timeframe combined with a narrow active trading window is a usability footgun, not a technical bug.** E.g. a 60-minute timeframe with the default 09:20–11:30 window only ever sees ~2 bar closes. Worth a UI hint (not a hard validation block) once this ships — noted here so it isn't forgotten, not required for a first version.

6. **Performance:** resampling ~1,875 rows (5 days of 1-minute data) into 7 timeframes, once per symbol per new 1-minute candle close (i.e. once a minute per symbol), is expected to be cheap — polars is columnar/vectorized and this is well within its normal use case. Should still be spot-checked once real (not synthetic) data volumes are in play, but is not expected to be a real bottleneck.

7. **Hardest things to test:** resampling correctness (boundary alignment, OHLC aggregation semantics — `open` = first, not min; `close` = last, not max; `volume` = sum) has no existing precedent anywhere in this codebase to lean on, unlike almost everything else built this session, which extended an established pattern. Budget real test-writing time here, with hand-constructed synthetic candle sequences where the expected resampled output can be verified by hand, the same style already used in `tests/unit/test_live_engine_warm_start.py`'s `make_candles()` helper.

---

## Dependencies on today's work (read this before starting)

This plan was written in the same session that shipped several other changes it directly builds on or assumes:

- **`StrategyConfig.start_time`/`end_time`** (added this session) is the direct template for how `timeframe` gets added: same migration style (`server_default` backfill, see `5f678bcbcdfa_add_active_window_to_deployments.py`), same API-layer validation style (a small regex/allowed-set check in `server/main.py::_validate_deployment_request`), same UI pattern (a new field in `DeploymentFieldsForm.tsx`, a new badge in `Strategies.tsx`). Read that migration and that form component first — they're the pattern to copy, not reinvent.

- **`LiveEngine.warm_start()` / `live/warm_start.py::warm_start_indicators()`** (added this session) is a *load-bearing dependency*, not just a nice-to-have: without it, every backend restart would leave higher timeframes needing hours of live ticks to warm up (see Risk #1 above), making multi-timeframe support nearly unusable in practice. This plan's design deliberately keeps `warm_start()` unchanged and lets it "just work" for multi-timeframe for free, by making `on_new_candle` itself timeframe-aware rather than adding a parallel warm-start path — that's a specific, deliberate choice worth preserving during implementation, not an accident to lose.

- **The capital-sufficiency validation and deployment-editing UI** (added this session — `DeploymentFieldsForm.tsx`, the inline edit mode in `Strategies.tsx`, `_validate_deployment_request` in `server/main.py`) is the pipeline the new `timeframe` field slots into. No new UI pattern is needed; extend the existing form/validation, don't build a parallel one.

- **"Restart-to-apply" is a long-standing, deliberate architectural choice** for this app (predates this session, reconfirmed multiple times today for watchlist changes, deployment edits, and strategy file edits). A `timeframe` change is restart-to-apply too, consistent with everything else — this is continuity, not a new limitation to design around.

- **Two unrelated ideas from earlier in this session that might sound related but aren't:** (a) fetching non-Indian "world market" data (Dow, Nasdaq, Nikkei, DXY) for the Market Analysis page — explicitly deferred, no relation to candle timeframes; (b) making the watchlist/deployment set "hot-reloadable" without a restart — a separate, still-unimplemented idea flagged during the active-window work. Neither is assumed or required by this plan; don't conflate them with this work while picking it back up.

- **`IndicatorCalculator` (`backtest/indicators.py`) was confirmed generic/timeframe-agnostic** by reading it during this planning session — it operates on whatever OHLCV DataFrame it's handed via talib, with no awareness of bar duration. No changes needed there; this was verified, not assumed.

---

## Verification (once implemented)

1. `python -m pytest tests/ -q` — full suite passes, including new resampling-correctness tests.
2. A dedicated test: feed `LiveEngine.warm_start()` a synthetic sequence of 1-minute candles spanning several hours with known, hand-computed values, and assert the resampled 5-minute/15-minute series has the exact expected bucket boundaries and OHLCV values.
3. Manually against the real running app: deploy the same strategy twice, once at 1-minute and once at 5-minute, on the same symbol, and confirm `GET /api/screener-live` (still 1-minute, unaffected) and each deployment's own entries reflect visibly different (and independently sensible) indicator values.
4. Confirm a fresh backend restart still warm-starts correctly for a deployment using a non-default timeframe — indicators for that timeframe should be available within seconds, not require live accumulation, mirroring the 1-minute warm-start proof from earlier this session.
5. `cd frontend && npm run build` clean; confirm the new dropdown appears in both the create form and inline edit mode, and that an existing deployment created before this change shows "1min" (the migrated default) without any manual fix-up.

---

## Post-implementation note: the O(n²) warm-start regression

The initial implementation called the full `on_new_candle()` (ingest + resample-every-timeframe-and-recompute) once per historical candle during `warm_start()`, exactly mirroring the live-tick path for simplicity. This was wrong in practice: resampling the whole (growing) 1-minute series across 6 timeframes is O(n) work, done once per candle across n candles = O(n²) for one symbol's warm-start. Measured effect: a 10-day/~3,000-candle backfill (needed once the 30-minute timeframe's warm-up requirement pushed `_LOOKBACK_DAYS` from 5 to 10) took over a minute per symbol and hadn't finished the first of 5 symbols after 60+ seconds — compared to the original single-timeframe warm-start's ~9 seconds for all 5 symbols combined.

Fix: `live/live_engine.py::LiveEngine.on_new_candle()` was split into `_ingest_candle()` (append + opening-range bookkeeping only — cheap, unavoidable per candle) and `_recompute_all_timeframes()` (the resample + indicator computation — expensive). The live tick path (`on_new_candle`, still called once per new candle) runs both, since one new candle is cheap to react to immediately. `warm_start()` now calls `_ingest_candle()` for every historical candle but `_recompute_all_timeframes()` only **once**, after the full batch — every intermediate snapshot during replay was already dead (never read before the next replay step overwrote it), so this changes nothing observable, just removes redundant work. Verified: 3,000 candles for one symbol dropped from "over a minute, not yet finished" to 1.86 seconds.

If this file is ever consulted for a *different* engine change that also iterates candle-by-candle (e.g. a future intraday backtester reusing `LiveEngine`), re-check whether it's paying this same O(n²) tax before assuming per-candle recomputation is "the simple, obviously-correct choice" — it's simple, but it wasn't actually correct-performance-wise at realistic data volumes.
