"""Sales use cases — orchestrate domain + repositories + events."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Callable, Optional

from alder.application.event_bus import EventBus
from alder.application.ports import UnitOfWork
from alder.application.services.pricing import PricingEngine
from alder.domain.entities import Client, PrintSpec, Sale, SaleItem
from alder.domain.events import OrderReady, SaleRegistered
from alder.domain.value_objects import SaleStatus

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DTOs — keep the framework layer's input shape decoupled from the domain.
# ---------------------------------------------------------------------------


@dataclass
class SaleItemInput:
    name: str
    quantity: int
    filament_grams: Decimal
    print_hours: Decimal
    customization_hours: Decimal = Decimal("0")
    painting_hours: Decimal = Decimal("0")


@dataclass
class RegisterSaleInput:
    client_id: int
    items: list[SaleItemInput]
    due_date: Optional[date] = None
    notes: str = ""


# ---------------------------------------------------------------------------
# Use cases
# ---------------------------------------------------------------------------


UowFactory = Callable[[], UnitOfWork]


class RegisterSaleUseCase:
    """Prices a new sale, persists it, then publishes ``SaleRegistered``."""

    def __init__(
        self,
        uow_factory: UowFactory,
        pricing: PricingEngine,
        event_bus: EventBus,
    ) -> None:
        self._uow_factory = uow_factory
        self._pricing = pricing
        self._bus = event_bus

    def execute(self, cmd: RegisterSaleInput) -> Sale:
        if not cmd.items:
            raise ValueError("A sale must have at least one item.")

        items = [
            SaleItem(
                name=i.name,
                quantity=i.quantity,
                spec=PrintSpec(
                    filament_grams=i.filament_grams,
                    print_hours=i.print_hours,
                    customization_hours=i.customization_hours,
                    painting_hours=i.painting_hours,
                ),
            )
            for i in cmd.items
        ]

        sale = Sale(
            client_id=cmd.client_id,
            items=items,
            status=SaleStatus.PENDING,
            due_date=cmd.due_date,
            notes=cmd.notes,
        )
        self._pricing.price_sale(sale)

        with self._uow_factory() as uow:
            if uow.clients.get(cmd.client_id) is None:
                raise LookupError(f"Client {cmd.client_id} does not exist.")
            persisted = uow.sales.add(sale)
            uow.commit()

        log.info(
            "Sale %s registered for client %s — total %s",
            persisted.id,
            persisted.client_id,
            persisted.total,
        )

        # IMPORTANT: publish AFTER commit. We must never trigger side effects
        # (Obsidian note, WhatsApp) if persistence rolled back.
        self._bus.publish(
            SaleRegistered(
                sale_id=persisted.id,  # type: ignore[arg-type]
                client_id=persisted.client_id,
                occurred_at=datetime.utcnow(),
            )
        )
        return persisted


class MarkOrderReadyUseCase:
    def __init__(self, uow_factory: UowFactory, event_bus: EventBus) -> None:
        self._uow_factory = uow_factory
        self._bus = event_bus

    def execute(self, sale_id: int) -> Sale:
        with self._uow_factory() as uow:
            sale = uow.sales.get(sale_id)
            if sale is None:
                raise LookupError(f"Sale {sale_id} not found.")
            sale.mark_ready()
            uow.sales.update(sale)
            uow.commit()

        log.info("Sale %s marked READY", sale_id)
        self._bus.publish(
            OrderReady(
                sale_id=sale_id,
                client_id=sale.client_id,
                occurred_at=datetime.utcnow(),
            )
        )
        return sale


class RegisterClientUseCase:
    def __init__(self, uow_factory: UowFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, client: Client) -> Client:
        with self._uow_factory() as uow:
            existing = uow.clients.get_by_phone(client.phone_e164)
            if existing is not None:
                return existing
            created = uow.clients.add(client)
            uow.commit()
            return created
