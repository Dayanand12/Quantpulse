from core.domain.enums import OrderSide
from infrastructure.events.in_process_event_bus import InProcessEventBus
from infrastructure.trading.paper_order_repository import PaperOrderRepository
from infrastructure.trading.paper_portfolio_service import PaperPortfolioService
from runners.paper_trading.paper_broker import PaperBroker


def test_portfolio_snapshot_reflects_capital_positions_and_trades():
    broker = PaperBroker(initial_capital=100_000)
    repo = PaperOrderRepository(broker, InProcessEventBus())
    service = PaperPortfolioService(broker)

    repo.open_position("RELIANCE", OrderSide.SELL, 250.0, 50)
    repo.open_position("TCS", OrderSide.SELL, 600.0, 50)
    repo.close_position("RELIANCE", 245.0)

    snapshot = service.get_status()

    assert snapshot.total_trades == 1
    assert snapshot.realized_pnl == 250.0
    assert len(snapshot.open_positions) == 1
    assert snapshot.open_positions[0].symbol == "TCS"
    assert snapshot.available_capital == broker.available_capital
