"""Pricing engine unit tests — pure, no I/O."""
from __future__ import annotations

from decimal import Decimal

import pytest

from alder.application.services.pricing import PricingEngine
from alder.domain.entities import PrintSpec, Sale, SaleItem


@pytest.fixture
def engine() -> PricingEngine:
    return PricingEngine()


def test_components_for_known_values(engine: PricingEngine) -> None:
    spec = PrintSpec(
        filament_grams=Decimal("100"),
        print_hours=Decimal("5"),
        customization_hours=Decimal("2"),
        painting_hours=Decimal("1"),
    )
    b = engine.price_item(spec, quantity=5)

    # material: 100 g × R$ 0.12 = R$ 12.00
    assert b.material_cost.amount == Decimal("12.00")
    # energy: 5 h × 0.15 kW × R$ 0.25 = R$ 0.1875 → 0.19
    # amort : 5 h × (3498 / 20000) = 0.8745 → 0.87
    # rent  : 5 h × (300 / 300)    = 5.00
    # total machine = 6.06
    assert b.machine_cost.amount == Decimal("6.06")
    # labour: 2 h × 20 + 1 h × 20 = 60
    assert b.labor_cost.amount == Decimal("60.00")
    # failure buffer: (12 + 6.06) × 0.15 = 2.709 → 2.71
    assert b.failure_buffer.amount == Decimal("2.71")
    # print cost: 12 + 6.06 + 2.71 = 20.77
    assert b.print_cost.amount == Decimal("20.77")
    # qty 5 → markup 4.0
    assert b.markup_multiplier == Decimal("4.0")
    # marked up print cost: 20.77 × 4 = 83.08
    assert b.marked_up_print_cost.amount == Decimal("83.08")
    # unit price: 83.08 + 60 = 143.08
    assert b.unit_price.amount == Decimal("143.08")
    # total: 143.08 × 5 = 715.40
    assert b.total.amount == Decimal("715.40")


@pytest.mark.parametrize(
    "qty,expected",
    [(1, Decimal("4.0")), (9, Decimal("4.0")),
     (10, Decimal("3.5")), (49, Decimal("3.5")),
     (50, Decimal("3.0")), (500, Decimal("3.0"))],
)
def test_markup_tiers(engine: PricingEngine, qty: int, expected: Decimal) -> None:
    spec = PrintSpec(filament_grams=Decimal("10"), print_hours=Decimal("1"))
    assert engine.price_item(spec, qty).markup_multiplier == expected


def test_failure_buffer_is_15_percent(engine: PricingEngine) -> None:
    spec = PrintSpec(filament_grams=Decimal("50"), print_hours=Decimal("2"))
    b = engine.price_item(spec, quantity=1)
    raw = b.material_cost + b.machine_cost
    ratio = b.failure_buffer.amount / raw.amount
    assert abs(ratio - Decimal("0.15")) < Decimal("0.01")


def test_price_sale_populates_every_item(engine: PricingEngine) -> None:
    items = [
        SaleItem(
            name="Dragon",
            quantity=3,
            spec=PrintSpec(filament_grams=Decimal("150"), print_hours=Decimal("4")),
        ),
        SaleItem(
            name="Keychain",
            quantity=60,
            spec=PrintSpec(filament_grams=Decimal("5"), print_hours=Decimal("0.25")),
        ),
    ]
    sale = Sale(client_id=1, items=items)
    engine.price_sale(sale)

    assert all(i.breakdown is not None for i in sale.items)
    # Different quantities should pick different markup tiers:
    assert sale.items[0].breakdown.markup_multiplier == Decimal("4.0")  # qty 3
    assert sale.items[1].breakdown.markup_multiplier == Decimal("3.0")  # qty 60
    assert sale.total.amount > 0


def test_invalid_quantity(engine: PricingEngine) -> None:
    with pytest.raises(ValueError):
        engine.price_item(PrintSpec(filament_grams=Decimal("1"), print_hours=Decimal("1")), 0)
