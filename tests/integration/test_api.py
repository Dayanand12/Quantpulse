from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from core.container import build_container
from core.domain.charges import ChargeConfig, compute_charges
from core.domain.enums import OrderSide
from infrastructure.config.settings import Environment, Settings
from infrastructure.persistence.database import Base, create_session_factory
from infrastructure.persistence.sql_watchlist_repository import SqlWatchlistRepository
from infrastructure.strategies.file_strategy_registry import FileStrategyRegistry
from infrastructure.strategies.filesystem_strategy_source_repository import (
    FilesystemStrategySourceRepository,
)
from server.main import create_app

DEFAULT_SYMBOLS = ("RELIANCE", "TCS")
SAMPLE_STRATEGY_SOURCE = "x = 1\n"

# A minimal, valid IStrategy — used to isolate registry-listing tests from
# whatever real files happen to be in the project's strategies/ folder
# (e.g. from manually testing the Strategy Builder tab).
MINIMAL_ORB_STRATEGY_SOURCE = """
from typing import Dict, List

from core.application.interfaces.strategy import IStrategy
from core.domain.enums import OrderSide


class TestOrbStrategy(IStrategy):
    name = "orb_reversal"
    display_name = "ORB Reversal (Short)"
    side = OrderSide.SELL

    def screen(self, snapshot: Dict[str, dict], symbols: List[str]) -> List[str]:
        return []
"""


def build_test_app(tmp_path, symbols=DEFAULT_SYMBOLS):
    database_url = f"sqlite:///{tmp_path / 'test.db'}"

    session_factory = create_session_factory(database_url)
    Base.metadata.create_all(session_factory().get_bind())
    # Pre-seed a watchlist so build_container's first-run seeding (which
    # falls back to reading the real Data_ingestion/stocks.json) never
    # kicks in — keeps this test isolated from that file's contents. This
    # also means build_container seeds Deployment 1 from these symbols.
    watchlist_repo = SqlWatchlistRepository(session_factory)
    default_watchlist = watchlist_repo.create_watchlist("Default")
    watchlist_repo.save_symbols(default_watchlist.id, list(symbols))

    settings = Settings(
        environment=Environment.TESTING, initial_capital=100_000, database_url=database_url
    )

    fake_client = MagicMock()
    fake_client.exchange = "NSE"
    fake_client.market_data = {}

    container = build_container(settings, fake_client)

    # build_container wires strategy_registry/strategy_source_repository to
    # the REAL strategies/ folder — swap in isolated tmp directories so
    # this test suite never reads/writes real project files, and listing
    # endpoints aren't affected by whatever strategies happen to exist
    # there in practice.
    registry_dir = tmp_path / "registry_strategies"
    registry_dir.mkdir()
    (registry_dir / "orb_reversal.py").write_text(MINIMAL_ORB_STRATEGY_SOURCE, encoding="utf-8")
    container.strategy_registry = FileStrategyRegistry(registry_dir)

    source_dir = tmp_path / "strategies"
    source_dir.mkdir()
    (source_dir / "orb_reversal.py").write_text(SAMPLE_STRATEGY_SOURCE, encoding="utf-8")
    container.strategy_source_repository = FilesystemStrategySourceRepository(source_dir)

    app = create_app(container, settings)
    return app, container


def make_deployment_payload(**overrides):
    payload = {
        "strategy_name": "orb_reversal",
        "symbols": ["RELIANCE"],
        "capital": 30_000,
        "quantity": 20,
        "stoploss_pct": 1.0,
        "target_pct": 3.0,
        "trailing_pct": 0.2,
        "max_cycles_per_day": 5,
    }
    payload.update(overrides)
    return payload


def test_root_and_live_status_endpoints(tmp_path):
    app, _ = build_test_app(tmp_path)

    with TestClient(app) as client:
        root = client.get("/")
        assert root.status_code == 200

        status = client.get("/api/live-status")
        assert status.status_code == 200
        body = status.json()
        assert body["available_capital"] == 100_000
        assert body["open_positions"] == {}
        assert body["trade_log"] == []


def test_positions_and_trades_reflect_seeded_deployment_state(tmp_path):
    app, container = build_test_app(tmp_path)
    runtime = container.deployment_runtimes[0]

    runtime.order_repository.open_position("RELIANCE", OrderSide.SELL, 250.0, 50)
    runtime.order_repository.close_position("RELIANCE", 245.0)

    with TestClient(app) as client:
        trades = client.get("/api/trades").json()
        assert len(trades) == 1
        assert trades[0]["symbol"] == "RELIANCE"
        assert trades[0]["pnl"] == 250.0
        assert trades[0]["deployment_id"] == runtime.deployment.id
        assert trades[0]["strategy_name"] == "orb_reversal"
        # Entry-context fields the Performance tab's per-strategy trades
        # drill-down needs to show where an entry worked vs. didn't.
        assert "closed_at" in trades[0]
        assert "market_condition" in trades[0]
        assert "entry_oi" in trades[0]
        # Real entry timestamp (not null) — needed to locate the trade on
        # an external chart, where closed_at alone only marks the exit.
        assert trades[0]["opened_at"] is not None

        positions = client.get("/api/positions").json()
        assert positions == []


def test_websocket_live_feed_delivers_expected_shape(tmp_path):
    app, _ = build_test_app(tmp_path)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/live") as ws:
            payload = ws.receive_json()

    assert set(payload.keys()) == {
        "snapshot",
        "stage_results",
        "broker_status",
        "positions",
        "market_ticker",
    }
    assert payload["stage_results"]["ORB"]["stage3"] == []


def test_market_ticker_computes_change_from_raw_ticks(tmp_path):
    app, container = build_test_app(tmp_path)

    # Simulate raw Zerodha ticks for an index — LTP + previous day's close
    # (Zerodha's OHLC "close" field), same shape Data_ingestion/client.py
    # populates. Indices report zero volume, so this deliberately doesn't
    # go anywhere near LiveEngine's indicator snapshot.
    container.market_data_provider._client.market_data = {
        "NIFTY 50": {"LTP": 24750.0, "Volume": 0, "C": 24500.0},
    }

    with TestClient(app) as client:
        with client.websocket_connect("/ws/live") as ws:
            payload = ws.receive_json()

    ticker = payload["market_ticker"]
    assert "NIFTY 50" in ticker
    assert ticker["NIFTY 50"]["ltp"] == 24750.0
    assert ticker["NIFTY 50"]["prev_close"] == 24500.0
    assert ticker["NIFTY 50"]["change"] == pytest.approx(250.0)
    assert ticker["NIFTY 50"]["change_pct"] == pytest.approx((250.0 / 24500.0) * 100)
    # NIFTY BANK is configured but has no tick yet — simply absent, not an error.
    assert "NIFTY BANK" not in ticker


def test_market_ticker_shows_ltp_without_change_when_prev_close_missing(tmp_path):
    app, container = build_test_app(tmp_path)

    container.market_data_provider._client.market_data = {
        "NIFTY 50": {"LTP": 24750.0, "Volume": 0},  # no "C" this tick
    }

    with TestClient(app) as client:
        with client.websocket_connect("/ws/live") as ws:
            payload = ws.receive_json()

    entry = payload["market_ticker"]["NIFTY 50"]
    assert entry["ltp"] == 24750.0
    assert entry["prev_close"] is None
    assert entry["change"] is None
    assert entry["change_pct"] is None


def test_watchlists_list_reflects_seeded_symbols(tmp_path):
    app, _ = build_test_app(tmp_path, symbols=["RELIANCE", "TCS", "INFY"])

    with TestClient(app) as client:
        body = client.get("/api/watchlists").json()

    assert len(body) == 1
    assert body[0]["name"] == "Default"
    assert body[0]["symbols"] == ["RELIANCE", "TCS", "INFY"]


def test_watchlist_create_rename_and_update_symbols(tmp_path):
    app, _ = build_test_app(tmp_path)

    with TestClient(app) as client:
        created = client.post("/api/watchlists", json={"name": "Bank Stocks"})
        assert created.status_code == 201
        watchlist_id = created.json()["id"]
        assert created.json()["symbols"] == []

        renamed = client.put(f"/api/watchlists/{watchlist_id}", json={"name": "Banking"})
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "Banking"

        updated = client.put(
            f"/api/watchlists/{watchlist_id}/symbols",
            json={"symbols": ["hdfcbank", " hdfcbank ", "icicibank"]},
        )
        assert updated.status_code == 200
        assert updated.json()["symbols"] == ["HDFCBANK", "ICICIBANK"]


def test_watchlist_create_rejects_duplicate_name(tmp_path):
    app, _ = build_test_app(tmp_path)

    with TestClient(app) as client:
        client.post("/api/watchlists", json={"name": "Default"})
        res = client.post("/api/watchlists", json={"name": "Default"})

    assert res.status_code == 400


def test_watchlist_symbols_put_rejects_empty_list(tmp_path):
    app, _ = build_test_app(tmp_path)

    with TestClient(app) as client:
        watchlist_id = client.get("/api/watchlists").json()[0]["id"]
        res = client.put(f"/api/watchlists/{watchlist_id}/symbols", json={"symbols": ["", "   "]})

    assert res.status_code == 400


def test_watchlist_delete_removes_it(tmp_path):
    app, _ = build_test_app(tmp_path)

    with TestClient(app) as client:
        second = client.post("/api/watchlists", json={"name": "Second"}).json()

        res = client.delete(f"/api/watchlists/{second['id']}")
        assert res.status_code == 200

        assert [w["name"] for w in client.get("/api/watchlists").json()] == ["Default"]


def test_watchlist_symbols_put_hot_adds_new_symbol_to_live_engine(tmp_path):
    app, container = build_test_app(tmp_path, symbols=["RELIANCE"])
    watchlist_id = container.watchlist_repository.list_watchlists()[0].id
    assert "TCS" not in container.live_engine.data  # not tracked yet

    with TestClient(app) as client:
        res = client.put(
            f"/api/watchlists/{watchlist_id}/symbols", json={"symbols": ["RELIANCE", "TCS"]}
        )
        assert res.status_code == 200

    # Hot-added synchronously (server/main.py::update_watchlist_symbols +
    # runners/paper_trading/hot_add.py) — no restart needed for the new
    # symbol to get data/or_data/indicator_snapshot slots.
    assert "TCS" in container.live_engine.data


def test_watchlist_symbols_put_does_not_re_add_already_tracked_symbols(tmp_path):
    app, container = build_test_app(tmp_path, symbols=["RELIANCE", "TCS"])
    watchlist_id = container.watchlist_repository.list_watchlists()[0].id
    original_data_object = container.live_engine.data["RELIANCE"]

    with TestClient(app) as client:
        res = client.put(
            f"/api/watchlists/{watchlist_id}/symbols", json={"symbols": ["RELIANCE", "TCS"]}
        )
        assert res.status_code == 200

    # Same object still — hot-add is a no-op for symbols already tracked,
    # never resets an existing symbol's accumulated candle data.
    assert container.live_engine.data["RELIANCE"] is original_data_object


def test_watchlist_delete_rejects_the_last_remaining_watchlist(tmp_path):
    app, _ = build_test_app(tmp_path)

    with TestClient(app) as client:
        only_id = client.get("/api/watchlists").json()[0]["id"]
        res = client.delete(f"/api/watchlists/{only_id}")

    assert res.status_code == 400


def test_symbol_search_returns_empty_before_any_resync(tmp_path):
    app, _ = build_test_app(tmp_path)

    with TestClient(app) as client:
        res = client.get("/api/symbols/search?q=REL")

    assert res.status_code == 200
    assert res.json() == []


def test_symbol_resync_populates_search_from_kite_instruments(tmp_path):
    app, container = build_test_app(tmp_path)
    container.zerodha_client.kite.instruments.return_value = [
        {"tradingsymbol": "RELIANCE", "name": "Reliance Industries Ltd", "instrument_type": "EQ"},
        {"tradingsymbol": "RELIANCE-BE", "name": "Reliance Industries Ltd", "instrument_type": "EQ"},
        {"tradingsymbol": "RELFUT", "name": "Reliance Futures", "instrument_type": "FUT"},
    ]

    with TestClient(app) as client:
        resync = client.post("/api/symbols/resync")
        assert resync.status_code == 200
        assert resync.json() == {"count": 2}  # the FUT row is filtered out

        results = client.get("/api/symbols/search?q=RELIANCE").json()

    assert {r["tradingsymbol"] for r in results} == {"RELIANCE", "RELIANCE-BE"}


def test_charge_config_get_returns_defaults_when_nothing_saved(tmp_path):
    app, _ = build_test_app(tmp_path)
    defaults = ChargeConfig()

    with TestClient(app) as client:
        body = client.get("/api/settings/charges").json()

    assert body["brokerage_pct"] == defaults.brokerage_pct
    assert body["gst_pct"] == defaults.gst_pct


def test_charge_config_put_saves_and_persists(tmp_path):
    app, _ = build_test_app(tmp_path)
    custom = {
        "brokerage_pct": 0.0005,
        "brokerage_max_per_order": 25.0,
        "stt_pct": 0.0003,
        "exchange_txn_pct": 0.00003,
        "sebi_pct": 0.000001,
        "stamp_duty_pct": 0.00004,
        "gst_pct": 0.18,
    }

    with TestClient(app) as client:
        res = client.put("/api/settings/charges", json=custom)
        assert res.status_code == 200
        assert res.json() == custom

        assert client.get("/api/settings/charges").json() == custom


def test_charge_config_put_rejects_negative_rate(tmp_path):
    app, _ = build_test_app(tmp_path)
    body = {
        "brokerage_pct": -0.0001,
        "brokerage_max_per_order": 20.0,
        "stt_pct": 0.00025,
        "exchange_txn_pct": 0.0000297,
        "sebi_pct": 0.000001,
        "stamp_duty_pct": 0.00003,
        "gst_pct": 0.18,
    }

    with TestClient(app) as client:
        res = client.put("/api/settings/charges", json=body)

    assert res.status_code == 422


def test_strategies_lists_discovered_strategies(tmp_path):
    app, _ = build_test_app(tmp_path)

    with TestClient(app) as client:
        body = client.get("/api/strategies").json()

    assert body == [{"name": "orb_reversal", "display_name": "ORB Reversal (Short)", "side": "SELL"}]


def test_strategy_source_list_and_get(tmp_path):
    app, _ = build_test_app(tmp_path)

    with TestClient(app) as client:
        assert client.get("/api/strategy-source").json() == ["orb_reversal"]

        body = client.get("/api/strategy-source/orb_reversal").json()
        assert body == {"name": "orb_reversal", "source": SAMPLE_STRATEGY_SOURCE}


def test_strategy_source_get_unknown_file_returns_404(tmp_path):
    app, _ = build_test_app(tmp_path)

    with TestClient(app) as client:
        res = client.get("/api/strategy-source/does_not_exist")

    assert res.status_code == 404


def test_strategy_source_create_and_then_get(tmp_path):
    app, _ = build_test_app(tmp_path)

    with TestClient(app) as client:
        res = client.post(
            "/api/strategy-source", json={"name": "my_strategy", "source": "y = 2\n"}
        )
        assert res.status_code == 201
        assert res.json() == {"name": "my_strategy", "source": "y = 2\n"}

        assert set(client.get("/api/strategy-source").json()) == {"orb_reversal", "my_strategy"}
        assert client.get("/api/strategy-source/my_strategy").json()["source"] == "y = 2\n"


def test_strategy_source_create_rejects_duplicate_name(tmp_path):
    app, _ = build_test_app(tmp_path)

    with TestClient(app) as client:
        res = client.post(
            "/api/strategy-source", json={"name": "orb_reversal", "source": "y = 2\n"}
        )

    assert res.status_code == 400


def test_strategy_source_create_rejects_invalid_syntax(tmp_path):
    app, _ = build_test_app(tmp_path)

    with TestClient(app) as client:
        res = client.post(
            "/api/strategy-source", json={"name": "broken", "source": "def f(:\n"}
        )
        assert res.status_code == 400

        assert "broken" not in client.get("/api/strategy-source").json()


def test_strategy_source_update_overwrites_existing_file(tmp_path):
    app, _ = build_test_app(tmp_path)

    with TestClient(app) as client:
        res = client.put("/api/strategy-source/orb_reversal", json={"source": "x = 99\n"})
        assert res.status_code == 200

        assert client.get("/api/strategy-source/orb_reversal").json()["source"] == "x = 99\n"


def test_strategy_source_update_unknown_file_returns_404(tmp_path):
    app, _ = build_test_app(tmp_path)

    with TestClient(app) as client:
        res = client.put("/api/strategy-source/does_not_exist", json={"source": "x = 1\n"})

    assert res.status_code == 404


def test_deployments_seeds_deployment_one_from_legacy_config(tmp_path):
    app, container = build_test_app(tmp_path, symbols=["RELIANCE", "TCS"])

    with TestClient(app) as client:
        body = client.get("/api/deployments").json()

    assert len(body) == 1
    seeded = body[0]
    assert seeded["strategy_name"] == "orb_reversal"
    assert seeded["symbols"] == ["RELIANCE", "TCS"]
    assert seeded["capital"] == 100_000
    assert seeded["quantity"] == 50
    assert seeded["stoploss_pct"] == 0.8
    assert seeded["running"] is True
    assert seeded["status"]["available_capital"] == 100_000
    assert seeded["id"] == container.deployment_runtimes[0].deployment.id
    # No trades yet — every metric is None (never a misleading 0).
    assert seeded["status"]["win_rate"] is None
    assert seeded["status"]["profit_factor"] is None
    assert seeded["status"]["avg_r_multiple"] is None
    assert seeded["status"]["sharpe_ratio"] is None
    assert seeded["status"]["max_drawdown"] == 0.0


def test_deployments_status_includes_performance_metrics_after_trades(tmp_path):
    app, container = build_test_app(tmp_path)
    runtime = container.deployment_runtimes[0]

    # Two trades, one win one loss, both with a stop-loss captured, so
    # win_rate/profit_factor/avg_r_multiple all become computable. Every
    # closed trade now has brokerage/STT/exchange/SEBI/stamp duty/GST
    # deducted (core/domain/charges.py, wired end-to-end via
    # build_container's real charge_config_repository) — profit_factor is
    # net of those, not the raw 250/150 price-difference ratio.
    runtime.order_repository.open_position("RELIANCE", OrderSide.SELL, 250.0, 50)
    runtime.order_repository.close_position("RELIANCE", 245.0, initial_stop_loss=252.0)
    runtime.order_repository.open_position("RELIANCE", OrderSide.SELL, 250.0, 50)
    runtime.order_repository.close_position("RELIANCE", 253.0, initial_stop_loss=252.0)

    with TestClient(app) as client:
        body = client.get("/api/deployments").json()

    default_config = ChargeConfig()
    win_charges = compute_charges(250.0, 245.0, 50, OrderSide.SELL, default_config).total
    loss_charges = compute_charges(250.0, 253.0, 50, OrderSide.SELL, default_config).total
    net_win = 250.0 - win_charges
    net_loss = -150.0 - loss_charges

    status = body[0]["status"]
    assert status["total_trades"] == 2
    assert status["win_rate"] == 50.0
    assert status["profit_factor"] == pytest.approx(net_win / abs(net_loss))
    assert status["avg_r_multiple"] is not None


def test_trades_today_filter_excludes_trades_from_other_days(tmp_path):
    import datetime as dt

    from infrastructure.persistence.database import unit_of_work
    from infrastructure.persistence.models import TradeRecord

    app, container = build_test_app(tmp_path)
    runtime = container.deployment_runtimes[0]

    # Inserted directly with controlled closed_at times rather than via
    # close_position() (which stamps real wall-clock datetime.now() —
    # today's date but not necessarily within the 09:15-15:30 market-hours
    # window /api/trades?today=true now filters to, see
    # infrastructure/persistence/sql_trade_repository.py's MARKET_OPEN/
    # MARKET_CLOSE bounds).
    today_market_hours = dt.datetime.combine(dt.date.today(), dt.time(11, 0))
    yesterday_market_hours = today_market_hours - dt.timedelta(days=1)

    with unit_of_work(container.session_factory) as session:
        session.add(
            TradeRecord(
                symbol="RELIANCE", side="SELL", quantity=50, entry_price=250.0, exit_price=245.0,
                pnl=250.0, closed_at=today_market_hours,
                deployment_id=runtime.deployment.id, strategy_name="orb_reversal",
            )
        )
        session.add(
            TradeRecord(
                symbol="TCS", side="SELL", quantity=10, entry_price=100.0, exit_price=95.0,
                pnl=50.0, closed_at=yesterday_market_hours,
                deployment_id=runtime.deployment.id, strategy_name="orb_reversal",
            )
        )

    with TestClient(app) as client:
        all_trades = client.get("/api/trades").json()
        today_trades = client.get("/api/trades", params={"today": "true"}).json()

    assert len(all_trades) == 2
    assert len(today_trades) == 1
    assert today_trades[0]["symbol"] == "RELIANCE"


def test_trades_strategy_filter_returns_only_that_strategy(tmp_path):
    import datetime as dt

    from infrastructure.persistence.database import unit_of_work
    from infrastructure.persistence.models import TradeRecord

    app, container = build_test_app(tmp_path)
    runtime = container.deployment_runtimes[0]
    closed_at = dt.datetime.combine(dt.date.today(), dt.time(11, 0))

    with unit_of_work(container.session_factory) as session:
        session.add(
            TradeRecord(
                symbol="RELIANCE", side="SELL", quantity=50, entry_price=250.0, exit_price=245.0,
                pnl=250.0, closed_at=closed_at,
                deployment_id=runtime.deployment.id, strategy_name="orb_reversal",
                market_condition="Trending / High Volume / Above VWAP",
            )
        )
        session.add(
            TradeRecord(
                symbol="TCS", side="SELL", quantity=10, entry_price=100.0, exit_price=105.0,
                pnl=-50.0, closed_at=closed_at,
                deployment_id=runtime.deployment.id, strategy_name="other_strategy",
            )
        )

    with TestClient(app) as client:
        orb_trades = client.get("/api/trades", params={"strategy": "orb_reversal"}).json()

    assert len(orb_trades) == 1
    assert orb_trades[0]["symbol"] == "RELIANCE"
    assert orb_trades[0]["strategy_name"] == "orb_reversal"
    assert orb_trades[0]["market_condition"] == "Trending / High Volume / Above VWAP"


def test_instrument_refs_endpoint_resolves_known_symbols_and_omits_unknown(tmp_path):
    app, container = build_test_app(tmp_path)

    def fake_find_instrument(symbol, exchange=None):
        if symbol == "RELIANCE":
            return {"instrument_token": 738561, "exchange": "NSE"}
        return None

    container.market_data_provider._client.find_instrument.side_effect = fake_find_instrument

    with TestClient(app) as client:
        result = client.get(
            "/api/instrument-refs", params={"symbols": "RELIANCE,UNKNOWN"}
        ).json()

    assert result["RELIANCE"] == {"instrument_token": 738561, "exchange": "NSE"}
    assert result["UNKNOWN"] is None


def test_trade_counts_survive_a_simulated_broker_restart(tmp_path):
    # Regression: total_trades/realized_pnl/win_rate on both /api/trades
    # and /api/deployments used to come from PaperBroker's in-memory
    # trade_log, which resets to empty on every backend restart even
    # though the trade was already durably persisted. Simulate a restart
    # by wiping the broker's own log directly (bypassing the journal) and
    # confirm both endpoints still see the trade via the persisted table.
    app, container = build_test_app(tmp_path)
    runtime = container.deployment_runtimes[0]

    runtime.order_repository.open_position("RELIANCE", OrderSide.SELL, 250.0, 50)
    runtime.order_repository.close_position("RELIANCE", 245.0)

    runtime.order_repository._broker.trade_log = []  # simulate a fresh restart's empty broker

    with TestClient(app) as client:
        trades = client.get("/api/trades").json()
        deployments = client.get("/api/deployments").json()

    assert len(trades) == 1
    assert trades[0]["symbol"] == "RELIANCE"

    # realized_pnl is net of charges (core/domain/charges.py) — see the
    # module docstring on this file's ChargeConfig import.
    expected_charges = compute_charges(250.0, 245.0, 50, OrderSide.SELL, ChargeConfig()).total
    status = deployments[0]["status"]
    assert status["total_trades"] == 1
    assert status["realized_pnl"] == pytest.approx(250.0 - expected_charges)
    assert status["gross_realized_pnl"] == 250.0


def test_create_deployment_succeeds_and_starts_running_immediately(tmp_path):
    app, container = build_test_app(tmp_path)

    with TestClient(app) as client:
        res = client.post("/api/deployments", json=make_deployment_payload())
        assert res.status_code == 201
        body = res.json()
        assert body["strategy_name"] == "orb_reversal"
        assert body["symbols"] == ["RELIANCE"]
        assert body["capital"] == 30_000

        # Hot: a new deployment gets a live ExecutionManager immediately,
        # no restart needed (server/main.py::_sync_deployment_runtime).
        listed = {d["id"]: d for d in client.get("/api/deployments").json()}
        assert listed[body["id"]]["running"] is True
        assert listed[body["id"]]["status"] is not None

    assert len(container.deployment_repository.list_deployments()) == 2
    assert len(container.deployment_runtimes) == 2


def test_create_deployment_rejects_unknown_strategy(tmp_path):
    app, _ = build_test_app(tmp_path)

    with TestClient(app) as client:
        res = client.post(
            "/api/deployments", json=make_deployment_payload(strategy_name="nope")
        )

    assert res.status_code == 400


def test_create_deployment_rejects_symbol_outside_watchlist(tmp_path):
    app, _ = build_test_app(tmp_path)

    with TestClient(app) as client:
        res = client.post(
            "/api/deployments", json=make_deployment_payload(symbols=["NOTLISTED"])
        )

    assert res.status_code == 400


def test_create_deployment_rejects_non_positive_capital(tmp_path):
    app, _ = build_test_app(tmp_path)

    with TestClient(app) as client:
        res = client.post("/api/deployments", json=make_deployment_payload(capital=0))

    assert res.status_code == 422


def test_create_deployment_defaults_active_window(tmp_path):
    app, _ = build_test_app(tmp_path)

    with TestClient(app) as client:
        res = client.post("/api/deployments", json=make_deployment_payload())

    assert res.json()["start_time"] == "09:20"
    assert res.json()["end_time"] == "11:30"


def test_create_deployment_accepts_custom_active_window(tmp_path):
    app, _ = build_test_app(tmp_path)

    with TestClient(app) as client:
        res = client.post(
            "/api/deployments",
            json=make_deployment_payload(start_time="13:00", end_time="15:00"),
        )

    assert res.status_code == 201
    assert res.json()["start_time"] == "13:00"
    assert res.json()["end_time"] == "15:00"


def test_create_deployment_rejects_start_time_after_end_time(tmp_path):
    app, _ = build_test_app(tmp_path)

    with TestClient(app) as client:
        res = client.post(
            "/api/deployments",
            json=make_deployment_payload(start_time="12:00", end_time="09:00"),
        )

    assert res.status_code == 400


def test_create_deployment_rejects_malformed_time(tmp_path):
    app, _ = build_test_app(tmp_path)

    with TestClient(app) as client:
        res = client.post(
            "/api/deployments", json=make_deployment_payload(start_time="9:20")
        )

    assert res.status_code == 422


def test_create_deployment_defaults_to_minute_timeframe(tmp_path):
    app, _ = build_test_app(tmp_path)

    with TestClient(app) as client:
        res = client.post("/api/deployments", json=make_deployment_payload())

    assert res.json()["timeframe"] == "minute"


def test_create_deployment_accepts_every_supported_timeframe(tmp_path):
    app, _ = build_test_app(tmp_path)

    with TestClient(app) as client:
        for timeframe in ("minute", "3minute", "5minute", "10minute", "15minute", "30minute"):
            res = client.post(
                "/api/deployments", json=make_deployment_payload(timeframe=timeframe)
            )
            assert res.status_code == 201, timeframe
            assert res.json()["timeframe"] == timeframe


def test_create_deployment_rejects_unsupported_timeframe(tmp_path):
    app, _ = build_test_app(tmp_path)

    with TestClient(app) as client:
        res = client.post(
            "/api/deployments", json=make_deployment_payload(timeframe="2minute")
        )

    assert res.status_code == 400


def test_update_deployment_accepts_a_new_timeframe(tmp_path):
    app, container = build_test_app(tmp_path)
    seeded_id = container.deployment_repository.list_deployments()[0].id

    with TestClient(app) as client:
        res = client.put(
            f"/api/deployments/{seeded_id}",
            json=make_deployment_payload(timeframe="5minute"),
        )

    assert res.status_code == 200
    assert res.json()["timeframe"] == "5minute"
    assert container.deployment_repository.get_deployment(seeded_id).config.timeframe == "5minute"


def test_update_deployment_overwrites_existing(tmp_path):
    app, container = build_test_app(tmp_path)
    seeded_id = container.deployment_repository.list_deployments()[0].id

    with TestClient(app) as client:
        res = client.put(
            f"/api/deployments/{seeded_id}",
            json=make_deployment_payload(symbols=["RELIANCE", "TCS"], capital=75_000),
        )
        assert res.status_code == 200
        assert res.json()["capital"] == 75_000

    updated = container.deployment_repository.get_deployment(seeded_id)
    assert updated.capital == 75_000
    assert updated.symbols == ("RELIANCE", "TCS")


def test_update_unknown_deployment_returns_404(tmp_path):
    app, _ = build_test_app(tmp_path)

    with TestClient(app) as client:
        res = client.put("/api/deployments/does-not-exist", json=make_deployment_payload())

    assert res.status_code == 404


def test_delete_deployment_removes_it(tmp_path):
    app, container = build_test_app(tmp_path)
    seeded_id = container.deployment_repository.list_deployments()[0].id
    assert len(container.deployment_runtimes) == 1  # seeded deployment starts running hot

    with TestClient(app) as client:
        res = client.delete(f"/api/deployments/{seeded_id}")
        assert res.status_code == 200

    assert container.deployment_repository.get_deployment(seeded_id) is None
    # Stopped live too, not just gone from the next restart onward — see
    # server/main.py::delete_deployment.
    assert container.deployment_runtimes == []


def test_update_deployment_hot_reloads_execution_manager_in_place(tmp_path):
    app, container = build_test_app(tmp_path, symbols=["RELIANCE", "TCS"])
    seeded_id = container.deployment_repository.list_deployments()[0].id
    runtime = next(rt for rt in container.deployment_runtimes if rt.deployment.id == seeded_id)
    original_execution_manager = runtime.execution_manager
    # Simulate an open position's tracked exit levels — mutating in place
    # (not replacing the ExecutionManager) is what's supposed to keep this
    # intact across a live edit.
    original_execution_manager.trade_state["RELIANCE"] = {
        "stop_loss": 100.0, "target": 90.0, "trail_price": 95.0,
    }

    with TestClient(app) as client:
        res = client.put(
            f"/api/deployments/{seeded_id}",
            json=make_deployment_payload(quantity=99, symbols=["RELIANCE", "TCS"]),
        )
        assert res.status_code == 200

    updated_runtime = next(rt for rt in container.deployment_runtimes if rt.deployment.id == seeded_id)
    assert updated_runtime.execution_manager is original_execution_manager
    assert updated_runtime.execution_manager.quantity == 99
    assert updated_runtime.execution_manager.trade_state["RELIANCE"]["stop_loss"] == 100.0


def test_update_deployment_disabling_stops_the_live_runtime(tmp_path):
    app, container = build_test_app(tmp_path)
    seeded_id = container.deployment_repository.list_deployments()[0].id
    assert len(container.deployment_runtimes) == 1

    with TestClient(app) as client:
        res = client.put(f"/api/deployments/{seeded_id}", json=make_deployment_payload(enabled=False))
        assert res.status_code == 200
        assert res.json()["enabled"] is False

    assert container.deployment_runtimes == []


def test_update_deployment_re_enabling_starts_it_again(tmp_path):
    app, container = build_test_app(tmp_path)
    seeded_id = container.deployment_repository.list_deployments()[0].id

    with TestClient(app) as client:
        client.put(f"/api/deployments/{seeded_id}", json=make_deployment_payload(enabled=False))
        assert container.deployment_runtimes == []

        res = client.put(f"/api/deployments/{seeded_id}", json=make_deployment_payload(enabled=True))
        assert res.status_code == 200

    assert len(container.deployment_runtimes) == 1


def test_update_deployment_changing_strategy_stops_rather_than_hot_swaps(tmp_path):
    app, container = build_test_app(tmp_path)
    seeded_id = container.deployment_repository.list_deployments()[0].id
    assert len(container.deployment_runtimes) == 1  # seeded deployment starts running hot

    second_strategy_source = MINIMAL_ORB_STRATEGY_SOURCE.replace(
        'name = "orb_reversal"', 'name = "orb_reversal_v2"'
    ).replace("class TestOrbStrategy", "class TestOrbStrategyV2")
    (tmp_path / "registry_strategies" / "orb_reversal_v2.py").write_text(
        second_strategy_source, encoding="utf-8"
    )
    # FileStrategyRegistry discovers *.py files once at construction — see
    # infrastructure/strategies/file_strategy_registry.py — so the new
    # file needs a fresh registry instance to be visible.
    container.strategy_registry = FileStrategyRegistry(tmp_path / "registry_strategies")

    with TestClient(app) as client:
        res = client.put(
            f"/api/deployments/{seeded_id}",
            json=make_deployment_payload(strategy_name="orb_reversal_v2"),
        )
        assert res.status_code == 200
        listed = {d["id"]: d for d in client.get("/api/deployments").json()}
        # DB says the new strategy; the live runtime is stopped rather
        # than silently running under the OLD strategy's logic with a
        # freshly-reset broker — see _sync_deployment_runtime's docstring.
        assert listed[seeded_id]["strategy_name"] == "orb_reversal_v2"
        assert listed[seeded_id]["running"] is False

    assert container.deployment_runtimes == []


def test_analytics_summary_with_no_trades_returns_empty_but_valid_shape(tmp_path):
    app, _ = build_test_app(tmp_path)

    with TestClient(app) as client:
        body = client.get("/api/analytics/summary").json()

    assert set(body.keys()) == {
        "overall", "by_strategy", "equity_curve", "pnl_by_period", "drawdown",
        "profit_distribution", "rolling_sharpe", "heatmap_strategy_symbol",
        "heatmap_strategy_condition", "strategy_trend", "strategy_correlation",
        "available_strategies", "available_symbols",
    }
    assert body["overall"]["total_trades"] == 0
    assert body["by_strategy"][0]["strategy_name"] == "orb_reversal"
    assert body["by_strategy"][0]["metrics"]["total_trades"] == 0
    assert body["equity_curve"] == []
    assert body["available_strategies"] == []
    assert body["available_symbols"] == []


def test_analytics_summary_reflects_closed_trades(tmp_path):
    app, container = build_test_app(tmp_path)
    runtime = container.deployment_runtimes[0]

    runtime.order_repository.open_position("RELIANCE", OrderSide.SELL, 250.0, 50)
    runtime.order_repository.close_position("RELIANCE", 245.0, initial_stop_loss=252.0)
    runtime.order_repository.open_position("TCS", OrderSide.SELL, 100.0, 10)
    runtime.order_repository.close_position("TCS", 105.0, initial_stop_loss=102.0)

    with TestClient(app) as client:
        body = client.get("/api/analytics/summary").json()

    assert body["overall"]["total_trades"] == 2
    assert body["overall"]["winning_trades"] == 1
    assert body["overall"]["losing_trades"] == 1
    assert body["available_symbols"] == ["RELIANCE", "TCS"]
    assert len(body["equity_curve"]) == 1  # both trades close same day -> one daily bucket
    assert len(body["profit_distribution"]) >= 1

    by_strategy = body["by_strategy"][0]
    assert by_strategy["strategy_name"] == "orb_reversal"
    assert by_strategy["metrics"]["total_trades"] == 2


def test_analytics_summary_distinguishes_same_strategy_on_two_timeframes(tmp_path):
    # Regression: deploying the same strategy twice (e.g. one on "minute",
    # one on "15minute") must produce two distinguishable by_strategy rows
    # — identical strategy_name, different deployment_id and timeframe.
    app, container = build_test_app(tmp_path)
    seeded_id = container.deployment_runtimes[0].deployment.id

    with TestClient(app) as client:
        created = client.post(
            "/api/deployments",
            json=make_deployment_payload(strategy_name="orb_reversal", timeframe="15minute"),
        )
        assert created.status_code == 201
        second_id = created.json()["id"]

        body = client.get("/api/analytics/summary").json()

    rows = {r["deployment_id"]: r for r in body["by_strategy"]}
    assert rows[seeded_id]["strategy_name"] == "orb_reversal"
    assert rows[seeded_id]["timeframe"] == "minute"
    assert rows[second_id]["strategy_name"] == "orb_reversal"
    assert rows[second_id]["timeframe"] == "15minute"


def test_trades_deployment_id_filter_distinguishes_same_strategy_deployments(tmp_path):
    app, container = build_test_app(tmp_path)
    first_runtime = container.deployment_runtimes[0]

    with TestClient(app) as client:
        created = client.post(
            "/api/deployments",
            json=make_deployment_payload(strategy_name="orb_reversal", timeframe="15minute"),
        )
        second_id = created.json()["id"]
        second_runtime = next(
            rt for rt in container.deployment_runtimes if rt.deployment.id == second_id
        )

        first_runtime.order_repository.open_position("RELIANCE", OrderSide.SELL, 250.0, 50)
        first_runtime.order_repository.close_position("RELIANCE", 245.0)
        second_runtime.order_repository.open_position("RELIANCE", OrderSide.SELL, 250.0, 50)
        second_runtime.order_repository.close_position("RELIANCE", 240.0)

        trades = client.get(
            "/api/trades", params={"deployment_id": second_id}
        ).json()

    assert len(trades) == 1
    assert trades[0]["deployment_id"] == second_id
    assert trades[0]["pnl"] == 500.0


def test_analytics_summary_filters_by_symbol(tmp_path):
    app, container = build_test_app(tmp_path)
    runtime = container.deployment_runtimes[0]

    runtime.order_repository.open_position("RELIANCE", OrderSide.SELL, 250.0, 50)
    runtime.order_repository.close_position("RELIANCE", 245.0)
    runtime.order_repository.open_position("TCS", OrderSide.SELL, 100.0, 10)
    runtime.order_repository.close_position("TCS", 105.0)

    with TestClient(app) as client:
        body = client.get("/api/analytics/summary", params={"symbol": "TCS"}).json()

    assert body["overall"]["total_trades"] == 1
    # Filter narrows the trade set, but option lists stay fully populated
    # (drawn from the unfiltered set) so dropdowns don't shrink under you.
    assert body["available_symbols"] == ["RELIANCE", "TCS"]


def test_create_deployment_allows_quantity_too_large_for_capital(tmp_path):
    # PaperBroker.enter() auto-downsizes an oversized quantity at trade time
    # instead of rejecting it, so this is no longer a deploy-time error.
    app, container = build_test_app(tmp_path)
    container.market_data_provider._client.market_data = {
        "TCS": {"LTP": 2447.0, "Volume": 1000},
    }

    with TestClient(app) as client:
        res = client.post(
            "/api/deployments",
            json=make_deployment_payload(symbols=["TCS"], capital=50_000, quantity=50),
        )

    assert res.status_code == 201


def test_create_deployment_accepts_when_capital_covers_quantity_at_live_price(tmp_path):
    app, container = build_test_app(tmp_path)
    container.market_data_provider._client.market_data = {
        "TCS": {"LTP": 2447.0, "Volume": 1000},
    }

    with TestClient(app) as client:
        res = client.post(
            "/api/deployments",
            json=make_deployment_payload(symbols=["TCS"], capital=50_000, quantity=15),
        )

    assert res.status_code == 201


def test_update_deployment_allows_quantity_too_large_for_capital(tmp_path):
    app, container = build_test_app(tmp_path)
    seeded_id = container.deployment_repository.list_deployments()[0].id
    container.market_data_provider._client.market_data = {
        "RELIANCE": {"LTP": 3000.0, "Volume": 1000},
    }

    with TestClient(app) as client:
        res = client.put(
            f"/api/deployments/{seeded_id}",
            json=make_deployment_payload(symbols=["RELIANCE"], capital=10_000, quantity=50),
        )

    assert res.status_code == 200


def test_deployments_status_surfaces_rejected_entries(tmp_path):
    app, container = build_test_app(tmp_path)
    runtime = container.deployment_runtimes[0]  # capital=100_000 by default seeding

    # Not even one share affordable — PaperBroker.enter() only truly
    # rejects (rather than auto-downsizing) at this extreme.
    runtime.order_repository.open_position("RELIANCE", OrderSide.SELL, 200_000.0, 1)

    with TestClient(app) as client:
        body = client.get("/api/deployments").json()

    rejected = body[0]["status"]["rejected_entries"]
    assert len(rejected) == 1
    assert rejected[0]["symbol"] == "RELIANCE"
    assert rejected[0]["reason"] == "insufficient_capital"
    assert rejected[0]["required_capital"] == pytest.approx(200_000.0)


def test_analytics_summary_rejects_invalid_timeframe(tmp_path):
    app, _ = build_test_app(tmp_path)

    with TestClient(app) as client:
        res = client.get("/api/analytics/summary", params={"timeframe": "hourly"})

    assert res.status_code == 400
