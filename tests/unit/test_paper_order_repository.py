from core.domain.charges import ChargeConfig, compute_charges
from core.domain.enums import OrderSide
from core.domain.events import PositionClosed, PositionOpened
from infrastructure.events.in_process_event_bus import InProcessEventBus
from infrastructure.trading.paper_order_repository import PaperOrderRepository
from runners.paper_trading.paper_broker import PaperBroker


class FakeChargeConfigRepository:
    def __init__(self, config=None):
        self._config = config or ChargeConfig()

    def get_config(self):
        return self._config

    def save_config(self, config):
        self._config = config
        return config


def make_repo(charge_config_repository=None):
    broker = PaperBroker(initial_capital=100_000)
    bus = InProcessEventBus()
    return (
        PaperOrderRepository(
            broker, bus, charge_config_repository=charge_config_repository
        ),
        bus,
    )


def test_open_position_succeeds_and_publishes_event():
    repo, bus = make_repo()
    opened = []
    bus.subscribe(PositionOpened, lambda e: opened.append(e.position))

    ok = repo.open_position("RELIANCE", OrderSide.SELL, 250.0, 50)

    assert ok is True
    assert opened[0].symbol == "RELIANCE"
    assert repo.get_open_position("RELIANCE").entry_price == 250.0


def test_open_position_auto_downsizes_when_requested_quantity_exceeds_capital():
    repo, _ = make_repo()

    # 10,000 shares @ 250 needs 2.5M — far more than the 100k capital —
    # so this fits by quantity, not by rejecting the entry.
    ok = repo.open_position("RELIANCE", OrderSide.SELL, 250.0, 10_000)

    assert ok is True
    assert repo.get_open_position("RELIANCE").quantity == 400  # floor(100_000 / 250)


def test_open_position_rejected_when_not_even_one_share_affordable():
    repo, _ = make_repo()

    ok = repo.open_position("RELIANCE", OrderSide.SELL, 200_000.0, 1)

    assert ok is False
    assert repo.get_open_position("RELIANCE") is None


def test_close_position_returns_trade_and_publishes_event():
    repo, bus = make_repo()
    closed = []
    bus.subscribe(PositionClosed, lambda e: closed.append(e.trade))

    repo.open_position("RELIANCE", OrderSide.SELL, 250.0, 50)
    trade = repo.close_position("RELIANCE", 245.0)

    assert trade.pnl == 250.0  # (250 - 245) * 50, short position
    assert closed == [trade]
    assert repo.get_open_position("RELIANCE") is None


def test_close_position_with_no_open_position_returns_none():
    repo, bus = make_repo()
    closed = []
    bus.subscribe(PositionClosed, lambda e: closed.append(e.trade))

    result = repo.close_position("RELIANCE", 245.0)

    assert result is None
    assert closed == []


def test_get_open_positions_lists_everything_open():
    repo, _ = make_repo()
    repo.open_position("RELIANCE", OrderSide.SELL, 250.0, 50)
    repo.open_position("TCS", OrderSide.SELL, 600.0, 50)

    symbols = {p.symbol for p in repo.get_open_positions()}

    assert symbols == {"RELIANCE", "TCS"}


def test_get_all_trades_reflects_trade_repository_interface():
    repo, _ = make_repo()
    repo.open_position("RELIANCE", OrderSide.SELL, 250.0, 50)
    repo.close_position("RELIANCE", 245.0)

    trades = repo.get_all()

    assert len(trades) == 1
    assert trades[0].symbol == "RELIANCE"


def test_close_position_initial_stop_loss_survives_a_fresh_read():
    # Regression: initial_stop_loss must persist into PaperBroker's own
    # trade_log (not just the object close_position() happens to return),
    # since get_all()/get_status() reconstruct Trade objects independently
    # on every call.
    repo, _ = make_repo()
    repo.open_position("RELIANCE", OrderSide.SELL, 250.0, 50)
    returned_trade = repo.close_position("RELIANCE", 245.0, initial_stop_loss=252.0)

    assert returned_trade.initial_stop_loss == 252.0

    reread_trade = repo.get_all()[0]
    assert reread_trade.initial_stop_loss == 252.0


def test_close_position_without_stop_loss_leaves_it_none():
    repo, _ = make_repo()
    repo.open_position("RELIANCE", OrderSide.SELL, 250.0, 50)
    repo.close_position("RELIANCE", 245.0)

    assert repo.get_all()[0].initial_stop_loss is None


def test_close_position_leaves_charges_none_without_a_charge_config_repository():
    repo, _ = make_repo()  # no charge_config_repository injected
    repo.open_position("RELIANCE", OrderSide.SELL, 250.0, 50)
    trade = repo.close_position("RELIANCE", 245.0)

    assert trade.charges is None
    assert trade.net_pnl is None


def test_close_position_computes_charges_when_charge_config_repository_is_injected():
    repo, _ = make_repo(charge_config_repository=FakeChargeConfigRepository())
    repo.open_position("RELIANCE", OrderSide.SELL, 250.0, 50)
    trade = repo.close_position("RELIANCE", 245.0)

    expected = compute_charges(250.0, 245.0, 50, OrderSide.SELL, ChargeConfig())

    assert trade.charges == expected.total
    assert trade.net_pnl == trade.pnl - expected.total
