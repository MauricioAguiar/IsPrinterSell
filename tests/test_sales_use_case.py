"""Use-case tests with in-memory fake repositories — no SQLAlchemy involved."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

import pytest

from alder.application.event_bus import EventBus
from alder.application.services.pricing import PricingEngine
from alder.application.services.sales import (
    MarkOrderReadyUseCase,
    RegisterSaleInput,
    RegisterSaleUseCase,
    SaleItemInput,
)
from alder.domain.entities import Client, Sale
from alder.domain.events import OrderReady, SaleRegistered
from alder.domain.value_objects import SaleStatus


# ---------------------------------------------------------------------------
# Fakes — satisfy the ports without touching a database.
# ---------------------------------------------------------------------------


class FakeClientRepo:
    def __init__(self) -> None:
        self._by_id: dict[int, Client] = {}
        self._next = 1

    def add(self, c: Client) -> Client:
        c.id = self._next
        self._next += 1
        self._by_id[c.id] = c
        return c

    def get(self, client_id: int) -> Optional[Client]:
        return self._by_id.get(client_id)

    def get_by_phone(self, phone: str) -> Optional[Client]:
        return next((c for c in self._by_id.values() if c.phone_e164 == phone), None)

    def list(self) -> list[Client]:
        return list(self._by_id.values())


class FakeSaleRepo:
    def __init__(self) -> None:
        self._by_id: dict[int, Sale] = {}
        self._next = 1

    def add(self, s: Sale) -> Sale:
        s.id = self._next
        self._next += 1
        self._by_id[s.id] = s
        return s

    def get(self, sale_id: int) -> Optional[Sale]:
        return self._by_id.get(sale_id)

    def list(self, *, limit: int = 100, offset: int = 0) -> list[Sale]:
        return list(self._by_id.values())[offset : offset + limit]

    def update(self, s: Sale) -> Sale:
        self._by_id[s.id] = s  # type: ignore[index]
        return s


class FakeUoW:
    def __init__(self) -> None:
        self.clients = FakeClientRepo()
        self.sales = FakeSaleRepo()
        self.committed = False

    def __enter__(self) -> "FakeUoW":
        return self

    def __exit__(self, *a) -> None:  # noqa: D401
        pass

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        pass


# Shared across factory calls so both use cases see the same data.
@pytest.fixture
def uow() -> FakeUoW:
    return FakeUoW()


@pytest.fixture
def uow_factory(uow: FakeUoW):
    return lambda: uow


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_register_sale_prices_and_publishes(uow, uow_factory, bus) -> None:
    client = uow.clients.add(Client(name="Ada", phone_e164="+5511999999999"))

    received: list = []
    bus.subscribe(SaleRegistered, received.append)

    uc = RegisterSaleUseCase(uow_factory, PricingEngine(), bus)
    cmd = RegisterSaleInput(
        client_id=client.id,  # type: ignore[arg-type]
        items=[
            SaleItemInput(
                name="Cube",
                quantity=3,
                filament_grams=Decimal("80"),
                print_hours=Decimal("3"),
            )
        ],
    )
    sale = uc.execute(cmd)

    assert sale.id == 1
    assert sale.total.amount > 0
    assert sale.items[0].breakdown is not None
    assert len(received) == 1
    assert received[0].sale_id == 1


def test_register_sale_rejects_unknown_client(uow_factory, bus) -> None:
    uc = RegisterSaleUseCase(uow_factory, PricingEngine(), bus)
    with pytest.raises(LookupError):
        uc.execute(
            RegisterSaleInput(
                client_id=999,
                items=[
                    SaleItemInput(
                        name="X",
                        quantity=1,
                        filament_grams=Decimal("1"),
                        print_hours=Decimal("1"),
                    )
                ],
            )
        )


def test_mark_ready_transitions_and_publishes(uow, uow_factory, bus) -> None:
    client = uow.clients.add(Client(name="Ada", phone_e164="+5511999999999"))
    register = RegisterSaleUseCase(uow_factory, PricingEngine(), bus)
    sale = register.execute(
        RegisterSaleInput(
            client_id=client.id,  # type: ignore[arg-type]
            items=[
                SaleItemInput(
                    name="X",
                    quantity=1,
                    filament_grams=Decimal("10"),
                    print_hours=Decimal("1"),
                )
            ],
        )
    )

    received: list = []
    bus.subscribe(OrderReady, received.append)

    ready_uc = MarkOrderReadyUseCase(uow_factory, bus)
    updated = ready_uc.execute(sale.id)  # type: ignore[arg-type]

    assert updated.status == SaleStatus.READY
    assert len(received) == 1
    assert received[0].sale_id == sale.id
