"""Default ICurrentUserProvider: one fixed local user.

The app is single-user today, so this is intentionally trivial. A real
multi-user implementation (session/JWT-backed, reading from persistence)
implements the same interface later — callers of ICurrentUserProvider don't
change.
"""

from core.application.interfaces.current_user_provider import CurrentUser, ICurrentUserProvider

_LOCAL_USER = CurrentUser(id="local", display_name="Local Trader")


class SingleUserProvider(ICurrentUserProvider):
    def get_current_user(self) -> CurrentUser:
        return _LOCAL_USER
