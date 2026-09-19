from core.application.interfaces.strategy import IStrategy
from core.domain.enums import OrderSide
from infrastructure.events.in_process_event_bus import InProcessEventBus
from infrastructure.trading.paper_order_repository import PaperOrderRepository
from runners.paper_trading.execution_manager import ExecutionManager
from runners.paper_trading.paper_broker import PaperBroker


class _FakeLiveEngine:
    def __init__(self, snapshot):
        self._snapshot = snapshot

    def get_snapshot(self, timeframe="minute"):
        return self._snapshot


class _FakeStrategy(IStrategy):
    name = "fake"
    display_name = "Fake"

    def __init__(self, side, candidates=None):
        self.side = side
        self.candidates = candidates or []

    def screen(self, snapshot, symbols):
        return [s for s in self.candidates if s in symbols]


def make_manager(snapshot, side=OrderSide.SELL, candidates=None, symbols=None, **kwargs):
    live_engine = _FakeLiveEngine(snapshot)
    strategy = _FakeStrategy(side, candidates if candidates is not None else ["RELIANCE"])
    repo = PaperOrderRepository(PaperBroker(100_000), InProcessEventBus())
    manager = ExecutionManager(
        live_engine, repo, strategy, symbols or ["RELIANCE"], **kwargs
    )
    return manager, repo, strategy


# ---------------------------------------------------------------------------
# SELL side — must match the tested backtest/config.py behavior exactly
# ---------------------------------------------------------------------------


def test_sell_enters_on_screened_candidate():
    snapshot = {"RELIANCE": {"ltp": 250.0}}
    manager, repo, _ = make_manager(snapshot, side=OrderSide.SELL)

    manager.evaluate()

    position = repo.get_open_position("RELIANCE")
    assert position is not None
    assert position.side == OrderSide.SELL
    assert position.entry_price == 250.0
    assert manager.trade_state["RELIANCE"]["stop_loss"] == 250.0 * 1.008
    assert manager.trade_state["RELIANCE"]["target"] == 250.0 * 0.98


def test_sell_exits_on_stop_loss_hit():
    snapshot = {"RELIANCE": {"ltp": 250.0}}
    manager, repo, strategy = make_manager(snapshot, side=OrderSide.SELL)

    manager.evaluate()  # enters at 250.0, SL at 252.0

    # A real screener would drop a symbol once price runs through the
    # stop-loss (it no longer satisfies the entry filters) — simulate that
    # so this test isolates the exit, not a same-cycle re-entry.
    strategy.candidates = []
    snapshot["RELIANCE"]["ltp"] = 253.0  # breach stop-loss
    manager.evaluate()

    assert repo.get_open_position("RELIANCE") is None
    trades = repo.get_all()
    assert len(trades) == 1
    assert trades[0].exit_price == 253.0


def test_exit_carries_the_entry_stop_loss_onto_the_resulting_trade():
    # Regression coverage for the metrics feature: the SL level computed
    # at entry must reach the closed Trade (for R-multiple), not just live
    # in ExecutionManager.trade_state and get discarded on exit.
    snapshot = {"RELIANCE": {"ltp": 250.0}}
    manager, repo, strategy = make_manager(snapshot, side=OrderSide.SELL)

    manager.evaluate()  # enters at 250.0, SL computed at 252.0
    expected_sl = manager.trade_state["RELIANCE"]["stop_loss"]

    strategy.candidates = []
    snapshot["RELIANCE"]["ltp"] = 253.0
    manager.evaluate()

    trade = repo.get_all()[0]
    assert trade.initial_stop_loss == expected_sl


def test_sell_exits_on_target_hit():
    snapshot = {"RELIANCE": {"ltp": 250.0}}
    manager, repo, strategy = make_manager(snapshot, side=OrderSide.SELL)

    manager.evaluate()  # enters at 250.0, target at 245.0

    strategy.candidates = []
    snapshot["RELIANCE"]["ltp"] = 244.0  # breach target
    manager.evaluate()

    assert repo.get_open_position("RELIANCE") is None
    assert repo.get_all()[0].exit_price == 244.0


def test_closed_trade_carries_the_entry_market_snapshot():
    # Regression coverage for the market-condition-on-trades feature: the
    # indicator snapshot the strategy actually saw at entry must reach the
    # closed Trade, end to end through PaperOrderRepository/PaperBroker.
    snapshot = {
        "RELIANCE": {"ltp": 250.0, "rsi": 28.0, "adx": 31.0, "atr_pct": 1.2, "vwap": 248.0, "volume_ratio": 2.0}
    }
    manager, repo, strategy = make_manager(snapshot, side=OrderSide.SELL)

    manager.evaluate()  # enters at 250.0

    strategy.candidates = []
    snapshot["RELIANCE"]["ltp"] = 244.0  # breach target
    manager.evaluate()

    trade = repo.get_all()[0]
    assert trade.entry_rsi == 28.0
    assert trade.entry_adx == 31.0
    assert trade.entry_atr_pct == 1.2
    assert trade.entry_vwap == 248.0
    assert trade.entry_volume_ratio == 2.0
    assert trade.market_condition == "Trending / High Volume / Above VWAP"


def test_closed_trade_carries_regime_fields_when_nifty_and_vix_are_tracked():
    # Regression coverage for the regime-logging feature: NIFTY 50/INDIA
    # VIX's own snapshots (present in the same multi-symbol `snapshot`
    # ExecutionManager already reads every cycle) must reach the closed
    # Trade's regime_trend/regime_volatility/index_trend/vix_bucket, end
    # to end through _manage_entries -> PaperOrderRepository/PaperBroker
    # -> mappers.trade_from_raw.
    snapshot = {
        "RELIANCE": {
            "ltp": 250.0, "rsi": 28.0, "adx": 31.0, "atr_pct": 1.2,
            "vwap": 248.0, "volume_ratio": 2.0, "ema9": 251.0, "ema21": 247.0,
        },
        "NIFTY 50": {
            "ltp": 24800.0, "ema9": 24700.0, "ema21": 24900.0,
            "adx": 15.0, "vwap": 24850.0, "atr_pct": 0.4,
        },
        "INDIA VIX": {"ltp": 12.0},
    }
    manager, repo, strategy = make_manager(snapshot, side=OrderSide.SELL)

    manager.evaluate()  # enters at 250.0

    strategy.candidates = []
    snapshot["RELIANCE"]["ltp"] = 244.0  # breach target
    manager.evaluate()

    trade = repo.get_all()[0]
    assert trade.regime_trend == "Bullish Trend"  # ema9>ema21 and ltp>vwap for RELIANCE
    assert trade.regime_volatility == "Normal"
    assert trade.index_trend == "Bearish Trend"  # NIFTY's own ema9<ema21 and ltp<vwap
    assert trade.vix_bucket == "Low"


def test_closed_trade_regime_fields_none_when_nifty_and_vix_not_tracked():
    snapshot = {"RELIANCE": {"ltp": 250.0}}
    manager, repo, strategy = make_manager(snapshot, side=OrderSide.SELL)

    manager.evaluate()

    strategy.candidates = []
    snapshot["RELIANCE"]["ltp"] = 244.0
    manager.evaluate()

    trade = repo.get_all()[0]
    assert trade.index_trend is None
    assert trade.vix_bucket is None


def test_does_not_reenter_symbol_already_open():
    snapshot = {"RELIANCE": {"ltp": 250.0}}
    manager, repo, _ = make_manager(snapshot, side=OrderSide.SELL)

    manager.evaluate()
    manager.evaluate()  # still screened, already open — must not re-enter

    assert len(repo.get_open_positions()) == 1


def test_respects_max_cycles_per_day():
    snapshot = {"RELIANCE": {"ltp": 250.0}}
    manager, repo, _ = make_manager(snapshot, side=OrderSide.SELL, max_cycles_per_day=1)

    manager.evaluate()  # cycle 1: enters
    snapshot["RELIANCE"]["ltp"] = 244.0
    manager.evaluate()  # cycle 1: exits on target

    snapshot["RELIANCE"]["ltp"] = 250.0
    manager.evaluate()  # would be cycle 2 — blocked by max_cycles_per_day

    assert repo.get_open_position("RELIANCE") is None
    assert len(repo.get_all()) == 1


# ---------------------------------------------------------------------------
# BUY side — the new, mirrored generalization
# ---------------------------------------------------------------------------


def test_buy_enters_on_screened_candidate():
    snapshot = {"RELIANCE": {"ltp": 250.0}}
    manager, repo, _ = make_manager(snapshot, side=OrderSide.BUY)

    manager.evaluate()

    position = repo.get_open_position("RELIANCE")
    assert position is not None
    assert position.side == OrderSide.BUY
    assert manager.trade_state["RELIANCE"]["stop_loss"] == 250.0 * 0.992
    assert manager.trade_state["RELIANCE"]["target"] == 250.0 * 1.02


def test_buy_exits_on_stop_loss_hit():
    snapshot = {"RELIANCE": {"ltp": 250.0}}
    manager, repo, strategy = make_manager(snapshot, side=OrderSide.BUY)

    manager.evaluate()  # enters at 250.0, SL at 248.0

    strategy.candidates = []
    snapshot["RELIANCE"]["ltp"] = 247.0  # breach stop-loss (price fell)
    manager.evaluate()

    assert repo.get_open_position("RELIANCE") is None
    assert repo.get_all()[0].exit_price == 247.0


def test_buy_exits_on_target_hit():
    snapshot = {"RELIANCE": {"ltp": 250.0}}
    manager, repo, strategy = make_manager(snapshot, side=OrderSide.BUY)

    manager.evaluate()  # enters at 250.0, target at 255.0

    strategy.candidates = []
    snapshot["RELIANCE"]["ltp"] = 256.0  # breach target (price rose)
    manager.evaluate()

    assert repo.get_open_position("RELIANCE") is None
    assert repo.get_all()[0].exit_price == 256.0


def test_buy_trailing_stop_ratchets_down_and_exits_on_pullback():
    snapshot = {"RELIANCE": {"ltp": 250.0}}
    manager, repo, strategy = make_manager(snapshot, side=OrderSide.BUY, trailing_pct=1.0)

    manager.evaluate()  # enters at 250.0

    # Price dips (favorable pullback for a BUY's trailing low-water mark)
    # but not enough to hit target/SL — trail_price should ratchet down.
    snapshot["RELIANCE"]["ltp"] = 249.0
    manager.evaluate()
    assert manager.trade_state["RELIANCE"]["trail_price"] == 249.0

    # Now price pops up more than trailing_pct above that low — exits.
    strategy.candidates = []
    snapshot["RELIANCE"]["ltp"] = 251.5
    manager.evaluate()

    assert repo.get_open_position("RELIANCE") is None
    assert repo.get_all()[0].exit_price == 251.5


# ---------------------------------------------------------------------------
# Timeframe pass-through
# ---------------------------------------------------------------------------


def test_evaluate_requests_the_configured_timeframe_from_live_engine():
    requested = []

    class _RecordingLiveEngine:
        def get_snapshot(self, timeframe="minute"):
            requested.append(timeframe)
            return {}

    strategy = _FakeStrategy(OrderSide.SELL, [])
    repo = PaperOrderRepository(PaperBroker(100_000), InProcessEventBus())
    manager = ExecutionManager(
        _RecordingLiveEngine(), repo, strategy, ["RELIANCE"], timeframe="15minute"
    )

    manager.evaluate()

    assert requested == ["15minute"]


def test_evaluate_defaults_to_minute_timeframe_when_not_configured():
    requested = []

    class _RecordingLiveEngine:
        def get_snapshot(self, timeframe="minute"):
            requested.append(timeframe)
            return {}

    strategy = _FakeStrategy(OrderSide.SELL, [])
    repo = PaperOrderRepository(PaperBroker(100_000), InProcessEventBus())
    manager = ExecutionManager(_RecordingLiveEngine(), repo, strategy, ["RELIANCE"])

    manager.evaluate()

    assert requested == ["minute"]


# ---------------------------------------------------------------------------
# watchlist_id binding — current_symbols() (core/domain/models.py::
# Deployment's docstring: watchlist_id, when set, is the real symbol
# source, re-read fresh every call instead of the frozen `symbols` list)
# ---------------------------------------------------------------------------


class _FakeWatchlistRepository:
    def __init__(self, symbols_by_id):
        self._symbols_by_id = symbols_by_id

    def get_symbols(self, watchlist_id):
        return list(self._symbols_by_id.get(watchlist_id, []))


def test_current_symbols_uses_the_frozen_list_when_no_watchlist_bound():
    manager, _, _ = make_manager({}, symbols=["RELIANCE", "INFY"])

    assert manager.current_symbols() == ["RELIANCE", "INFY"]


def test_current_symbols_resolves_from_the_watchlist_when_bound():
    watchlists = _FakeWatchlistRepository({7: ["WIPRO", "TCS"]})
    manager, _, _ = make_manager(
        {},
        symbols=["RELIANCE"],  # present but must be ignored — watchlist_id wins
        watchlist_repository=watchlists,
        watchlist_id=7,
    )

    assert manager.current_symbols() == ["WIPRO", "TCS"]


def test_current_symbols_reflects_a_watchlist_edit_on_the_very_next_call():
    # No caching — a watchlist edit takes effect on this deployment's next
    # 3-second cycle (deployment_runner.py), not on the next restart, the
    # way editing a strategy's own conditions.json would require.
    watchlists = _FakeWatchlistRepository({7: ["WIPRO"]})
    manager, _, _ = make_manager(
        {}, watchlist_repository=watchlists, watchlist_id=7,
    )

    assert manager.current_symbols() == ["WIPRO"]

    watchlists._symbols_by_id[7] = ["WIPRO", "ASIANPAINT"]

    assert manager.current_symbols() == ["WIPRO", "ASIANPAINT"]


def test_evaluate_screens_the_watchlists_current_symbols_when_bound():
    watchlists = _FakeWatchlistRepository({7: ["WIPRO"]})
    snapshot = {"WIPRO": {"ltp": 400.0}, "RELIANCE": {"ltp": 250.0}}
    manager, repo, strategy = make_manager(
        snapshot,
        side=OrderSide.BUY,
        candidates=["WIPRO", "RELIANCE"],  # strategy would take both — only WIPRO is in the watchlist
        watchlist_repository=watchlists,
        watchlist_id=7,
    )

    manager.evaluate()

    assert repo.get_open_position("WIPRO") is not None
    assert repo.get_open_position("RELIANCE") is None
