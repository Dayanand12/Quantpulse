"""Port: identify who is making the current request.

Minimal auth seam only — the app is single-user today. The default adapter
(infrastructure/auth/single_user_provider.py) always returns one local user.
A real multi-user implementation (sessions, JWT, per-user data isolation)
slots in behind this same interface later; nothing that calls
ICurrentUserProvider needs to change when that happens.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class CurrentUser:
    id: str
    display_name: str


class ICurrentUserProvider(ABC):
    @abstractmethod
    def get_current_user(self) -> CurrentUser:
        """Return the identity of the current user."""
