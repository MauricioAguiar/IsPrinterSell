"""SQLAlchemy engine + session configuration."""
from __future__ import annotations

import os
from typing import Optional

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base


_engine: Optional[Engine] = None
_SessionFactory: Optional[sessionmaker[Session]] = None


def _enable_sqlite_wal(dbapi_connection, _):  # pragma: no cover - setup hook
    """Reduce ``database is locked`` errors under concurrent writes.

    WAL + busy_timeout is the canonical SQLite-for-web-apps setup.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def get_engine(url: Optional[str] = None) -> Engine:
    global _engine, _SessionFactory
    if _engine is not None:
        return _engine

    from sqlalchemy import create_engine

    database_url = url or os.getenv("ALDER_DATABASE_URL", "sqlite:///./alder.db")
    is_sqlite = database_url.startswith("sqlite")

    _engine = create_engine(
        database_url,
        echo=False,
        future=True,
        connect_args={"check_same_thread": False} if is_sqlite else {},
    )
    if is_sqlite:
        event.listen(_engine, "connect", _enable_sqlite_wal)

    _SessionFactory = sessionmaker(
        bind=_engine, autoflush=False, expire_on_commit=False, future=True
    )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    if _SessionFactory is None:
        get_engine()
    assert _SessionFactory is not None
    return _SessionFactory


def init_schema() -> None:
    """Create all tables. Idempotent — safe to call on every boot."""
    Base.metadata.create_all(get_engine())
