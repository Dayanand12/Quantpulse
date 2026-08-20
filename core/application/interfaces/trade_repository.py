"""Port: read-side query over persisted closed trades.

Complements SqlTradeJournal (write-only, event-driven — see
infrastructure/persistence/sql_trade_journal.py) with the read path
analytics needs: querying the `trades` table with filters, across
restarts and past/deleted deployments, not just PaperBroker's in-memory
current-session trade_log.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from core.domain.models import Trade


@dataclass(frozen=True)
class TradeFilter:
    strategy_name: Optional[str] = None
    symbol: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None  # inclusive
    # Narrows to one deployment — matters when the same strategy_name is
    # deployed more than once (e.g. the same strategy on two different
    # timeframes), where strategy_name alone can't tell the trades apart.
    deployment_id: Optional[str] = None


class ITradeRepository(ABC):
    @abstractmethod
    def list_trades(self, filters: Optional[TradeFilter] = None) -> List[Trade]:
        """Every closed trade matching filters, ordered by closed_at."""
