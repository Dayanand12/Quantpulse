"""SQLAlchemy engine/session scaffolding.

Nothing in the running app uses this yet — the default repositories
(infrastructure/trading/paper_order_repository.py) are in-memory, wrapping
the existing PaperBroker. This exists so a future SQL-backed repository
implementation is a matter of writing one new adapter class + an Alembic
migration, not standing up persistence from scratch under time pressure.
"""

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def create_session_factory(database_url: str) -> sessionmaker:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args)
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
