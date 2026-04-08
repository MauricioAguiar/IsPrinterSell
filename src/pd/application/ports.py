"""Ports — interfaces the application layer depends on.

Concrete implementations live in ``alder.infrastructure``. The domain and
application layers never import anything from infrastructure; they only
depend on these Protocols.
"""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Iterable, Optional, Protocol, runtime_checkable

from alder.domain.entities import Client, Sale


# ---------------------------------------------------------------------------
# Repositories
# ---------------------------------------------------------------------------


@runtime_checkable
class ClientRepository(Protocol):
    def add(self, client: Client) -> Client: ...
    def get(self, client_id: int) -> Optional[Client]: ...
    def get_by_phone(self, phone_e164: str) -> Optional[Client]: ...
    def list(self) -> list[Client]: ...


@runtime_checkable
class SaleRepository(Protocol):
    def add(self, sale: Sale) -> Sale: ...
    def get(self, sale_id: int) -> Optional[Sale]: ...
    def list(self, *, limit: int = 100, offset: int = 0) -> list[Sale]: ...
    def update(self, sale: Sale) -> Sale: ...


# ---------------------------------------------------------------------------
# Unit of Work — atomic transaction boundary
# ---------------------------------------------------------------------------


class UnitOfWork(AbstractContextManager["UnitOfWork"], Protocol):
    """Bundles repositories under a single transaction.

    Usage::

        with uow_factory() as uow:
            uow.clients.add(client)
            uow.sales.add(sale)
            uow.commit()  # otherwise rolled back on __exit__
    """

    clients: ClientRepository
    sales: SaleRepository

    def commit(self) -> None: ...
    def rollback(self) -> None: ...


# ---------------------------------------------------------------------------
# Outbound integrations
# ---------------------------------------------------------------------------


class ObsidianPort(Protocol):
    def write_sale_note(self, sale: Sale, client: Client) -> str:
        """Return the absolute path of the file written."""


class WhatsAppPort(Protocol):
    def send_text(self, phone_e164: str, body: str) -> None: ...


# ---------------------------------------------------------------------------
# Async task runner
# ---------------------------------------------------------------------------


class TaskRunner(Protocol):
    def submit(self, fn, /, *args, **kwargs) -> None:
        """Fire-and-forget task dispatch. Must not raise for caller."""

    def shutdown(self, *, wait: bool = True) -> None: ...
