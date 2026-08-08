"""Port: the editable brokerage/tax rate card used to compute realized P&L
net of charges (see core/domain/charges.py). Today's adapter is SQL-backed
(infrastructure/persistence) — a single row, since there's one rate card
for the whole account.
"""

from abc import ABC, abstractmethod

from core.domain.charges import ChargeConfig


class IChargeConfigRepository(ABC):
    @abstractmethod
    def get_config(self) -> ChargeConfig:
        """Currently configured rates. Returns ChargeConfig() defaults if
        nothing has been saved yet."""

    @abstractmethod
    def save_config(self, config: ChargeConfig) -> ChargeConfig:
        """Replace the rate card. Takes effect on the next trade closed —
        does not retroactively recompute already-closed trades."""
