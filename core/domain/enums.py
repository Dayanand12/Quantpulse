"""Framework-agnostic enums shared across every module.

These describe concepts of the trading domain itself (a side, a status, a
mode) — they must never import anything from infrastructure, application,
or a specific broker/UI. That is what keeps the domain reusable across
paper trading, live trading, and backtesting alike.
"""

from enum import Enum


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class TradingMode(str, Enum):
    PAPER = "PAPER"
    LIVE = "LIVE"
    BACKTEST = "BACKTEST"


class NotificationLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
