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


class ITradeRepository(ABC):
    @abstractmethod
    def list_trades(self, filters: Optional[TradeFilter] = None) -> List[Trade]:
        """Every closed trade matching filters, ordered by closed_at."""
