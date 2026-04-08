"""SQLAlchemy-backed Unit of Work.

Wraps a session + all repositories under a single transaction. Retries the
whole block once on SQLite ``database is locked`` conditions — cheap and
sufficient for a single-user desktop ERP.
"""
from __future__ import annotations

import logging
import time
from types import TracebackType
from typing import Optional, Type

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from alder.infrastructure.repositories.client_repo import SqlAlchemyClientRepository
from alder.infrastructure.repositories.sale_repo import SqlAlchemySaleRepository

from .session import get_session_factory

log = logging.getLogger(__name__)


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory=None) -> None:
        self._factory = session_factory or get_session_factory()
        self._session: Optional[Session] = None
        self.clients: SqlAlchemyClientRepository  # type: ignore[assignment]
        self.sales: SqlAlchemySaleRepository  # type: ignore[assignment]

    # Context manager ---------------------------------------------------------
    def __enter__(self) -> "SqlAlchemyUnitOfWork":
        self._session = self._factory()
        self.clients = SqlAlchemyClientRepository(self._session)
        self.sales = SqlAlchemySaleRepository(self._session)
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        assert self._session is not None
        try:
            if exc is not None:
                self._session.rollback()
        finally:
            self._session.close()
            self._session = None

    # Commit/rollback ---------------------------------------------------------
    def commit(self) -> None:
        assert self._session is not None
        last_err: Optional[Exception] = None
        for attempt in range(3):
            try:
                self._session.commit()
                return
            except OperationalError as e:  # pragma: no cover - hard to reproduce
                msg = str(e.orig) if e.orig else str(e)
                if "locked" not in msg.lower():
                    raise
                last_err = e
                backoff = 0.05 * (2**attempt)
                log.warning(
                    "DB locked on commit (attempt %s) — retrying in %.2fs",
                    attempt + 1,
                    backoff,
                )
                time.sleep(backoff)
        assert last_err is not None
        raise last_err

    def rollback(self) -> None:
        assert self._session is not None
        self._session.rollback()
