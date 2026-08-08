"""SQLAlchemy engine/session scaffolding.

Nothing in the running app uses this yet — the default repositories
(infrastructure/trading/paper_order_repository.py) are in-memory, wrapping
the existing PaperBroker. This exists so a future SQL-backed repository
implementation is a matter of writing one new adapter class + an Alembic
migration, not standing up persistence from scratch under time pressure.
"""

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def create_session_factory(database_url: str) -> sessionmaker:
    is_sqlite = database_url.startswith("sqlite")
    connect_args = {"check_same_thread": False} if is_sqlite else {}
    engine = create_engine(database_url, connect_args=connect_args)

    if is_sqlite:
        # WAL: writers no longer block readers, and a crash mid-write
        # rolls back cleanly on next open instead of leaving a torn page
        # (the "database disk image is malformed" corruption this app hit
        # once already, on the old OneDrive-hosted db).
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def unit_of_work(session_factory: sessionmaker) -> Iterator[Session]:
    """One transaction per `with` block: commit on success, rollback on error."""
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
