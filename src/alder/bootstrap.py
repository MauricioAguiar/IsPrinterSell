"""Composition root.

This is the ONLY place where the concrete adapters are wired into the
application's ports. Everything else depends on abstractions.
"""
from __future__ import annotations

import logging
import os

from alder.application.event_bus import EventBus
from alder.application.services.pricing import PricingEngine
from alder.application.services.sales import (
    MarkOrderReadyUseCase,
    RegisterClientUseCase,
    RegisterSaleUseCase,
)
from alder.domain.events import OrderReady, SaleRegistered
from alder.infrastructure.async_runner import ThreadPoolTaskRunner
from alder.infrastructure.db.session import init_schema
from alder.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from alder.infrastructure.obsidian.vault_writer import ObsidianVaultWriter
from alder.infrastructure.whatsapp.meta_cloud import WhatsAppCloudClient

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Container
# ---------------------------------------------------------------------------


class Container:
    """Process-wide dependency container.

    Django views look this up via :func:`get_container`. Keep it small —
    only factories and singletons that must be shared across requests.
    """

    def __init__(self) -> None:
        self.event_bus = EventBus()
        self.task_runner = ThreadPoolTaskRunner()
        self.pricing_engine = PricingEngine()

        self.obsidian = ObsidianVaultWriter(
            vault_root=os.getenv("ALDER_OBSIDIAN_VAULT", "./obsidian_vault"),
            subdir=os.getenv("ALDER_OBSIDIAN_SALES_SUBDIR", "Sales"),
        )
        self.whatsapp = WhatsAppCloudClient()

        self.uow_factory = SqlAlchemyUnitOfWork  # callable that returns a UoW

        # Use cases ---------------------------------------------------------
        self.register_sale = RegisterSaleUseCase(
            self.uow_factory, self.pricing_engine, self.event_bus
        )
        self.mark_order_ready = MarkOrderReadyUseCase(
            self.uow_factory, self.event_bus
        )
        self.register_client = RegisterClientUseCase(self.uow_factory)

        self._wire_event_handlers()

    # ------------------------------------------------------------------ #
    # Event wiring — all side effects are fire-and-forget.
    # ------------------------------------------------------------------ #
    def _wire_event_handlers(self) -> None:
        self.event_bus.subscribe(SaleRegistered, self._on_sale_registered)
        self.event_bus.subscribe(OrderReady, self._on_order_ready)

    def _on_sale_registered(self, event: SaleRegistered) -> None:
        # We capture the sale_id only; the background worker re-fetches the
        # aggregate via its own UoW. Passing live ORM objects across threads
        # is a classic footgun.
        def job() -> None:
            with self.uow_factory() as uow:
                sale = uow.sales.get(event.sale_id)
                if sale is None:
                    log.error(
                        "SaleRegistered fired for missing sale %s", event.sale_id
                    )
                    return
                client = uow.clients.get(sale.client_id)
                if client is None:
                    log.error(
                        "Sale %s references missing client %s",
                        sale.id,
                        sale.client_id,
                    )
                    return
            # Writing to the vault is pure I/O — done outside the DB session.
            self.obsidian.write_sale_note(sale, client)

        self.task_runner.submit(job)

    def _on_order_ready(self, event: OrderReady) -> None:
        def job() -> None:
            with self.uow_factory() as uow:
                sale = uow.sales.get(event.sale_id)
                client = uow.clients.get(event.client_id) if sale else None
            if sale is None or client is None:
                log.error("OrderReady references missing sale/client")
                return
            body = (
                f"Ola {client.name}! Seu pedido #{sale.id:05d} esta pronto "
                f"para retirada. Total: {sale.total}. Obrigado!"
            )
            self.whatsapp.send_text(client.phone_e164, body)

        self.task_runner.submit(job)


# ---------------------------------------------------------------------------
# Module-level accessor — lazy so tests can reset it.
# ---------------------------------------------------------------------------

_container: Container | None = None


def get_container() -> Container:
    global _container
    if _container is None:
        _container = Container()
    return _container


def reset_container() -> None:
    """Only for tests."""
    global _container
    if _container is not None:
        _container.task_runner.shutdown(wait=False)
    _container = None


def init_db() -> None:
    """CLI helper — create schema."""
    init_schema()
