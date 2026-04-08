"""Pricing engine — pure functions on domain value objects.

Encodes the constants supplied by the business:

* Filament cost            R$ 120.00 / kg  -> R$ 0.12 / g
* Printer max power        150 W           -> 0.15 kW
* Energy cost              R$ 0.25 / kWh
* Printer value            R$ 3 498.00
* Printer lifespan         20 000 h
* Monthly rent / amortisation  R$ 300.00
* Customisation labour     R$ 20.00 / h
* Painting labour          R$ 20.00 / h
* Failure safety margin    15 % applied to (material + machine) cost
* Dynamic markup           qty < 10  -> x4.0
                           qty < 50  -> x3.5
                           qty >= 50 -> x3.0

The markup is applied to the *print cost* (material + machine + failure
buffer). Labour is added on top as a pass-through — painting/customisation
fees shouldn't be multiplied by 4x.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from alder.domain.entities import PrintSpec, Sale
from alder.domain.value_objects import CostBreakdown, Money


# ---------------------------------------------------------------------------
# Constants — tweak in one place only.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PricingConstants:
    filament_brl_per_gram: Decimal = Decimal("0.12")  # 120 BRL / 1000 g

    printer_power_kw: Decimal = Decimal("0.150")  # 150 W
    energy_brl_per_kwh: Decimal = Decimal("0.25")

    printer_value_brl: Decimal = Decimal("3498.00")
    printer_lifespan_hours: Decimal = Decimal("20000")

    monthly_rent_brl: Decimal = Decimal("300.00")
    # Assumed monthly productive hours — 10 h/day * 30 days. Adjust to taste.
    monthly_productive_hours: Decimal = Decimal("300")

    customisation_brl_per_hour: Decimal = Decimal("20.00")
    painting_brl_per_hour: Decimal = Decimal("20.00")

    failure_margin: Decimal = Decimal("0.15")

    markup_small: Decimal = Decimal("4.0")   # qty < 10
    markup_medium: Decimal = Decimal("3.5")  # qty < 50
    markup_large: Decimal = Decimal("3.0")   # qty >= 50


DEFAULTS = PricingConstants()


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class PricingEngine:
    """Deterministic, side-effect-free cost calculator."""

    def __init__(self, constants: PricingConstants = DEFAULTS) -> None:
        self.c = constants

    # -- individual components -------------------------------------------------

    def _material_cost(self, spec: PrintSpec) -> Money:
        return Money.of(spec.filament_grams * self.c.filament_brl_per_gram)

    def _energy_cost(self, spec: PrintSpec) -> Money:
        return Money.of(
            spec.print_hours * self.c.printer_power_kw * self.c.energy_brl_per_kwh
        )

    def _printer_amortisation(self, spec: PrintSpec) -> Money:
        rate = self.c.printer_value_brl / self.c.printer_lifespan_hours
        return Money.of(spec.print_hours * rate)

    def _rent_allocation(self, spec: PrintSpec) -> Money:
        rate = self.c.monthly_rent_brl / self.c.monthly_productive_hours
        return Money.of(spec.print_hours * rate)

    def _machine_cost(self, spec: PrintSpec) -> Money:
        return (
            self._energy_cost(spec)
            + self._printer_amortisation(spec)
            + self._rent_allocation(spec)
        )

    def _labor_cost(self, spec: PrintSpec) -> Money:
        return Money.of(
            spec.customization_hours * self.c.customisation_brl_per_hour
            + spec.painting_hours * self.c.painting_brl_per_hour
        )

    def _markup_for_quantity(self, qty: int) -> Decimal:
        if qty < 10:
            return self.c.markup_small
        if qty < 50:
            return self.c.markup_medium
        return self.c.markup_large

    # -- public API -----------------------------------------------------------

    def price_item(self, spec: PrintSpec, quantity: int) -> CostBreakdown:
        if quantity <= 0:
            raise ValueError("quantity must be > 0")

        material = self._material_cost(spec)
        machine = self._machine_cost(spec)
        labor = self._labor_cost(spec)

        # 15% safety buffer applied to the machine+material portion only.
        failure_buffer = (material + machine) * self.c.failure_margin

        print_cost = material + machine + failure_buffer
        markup = self._markup_for_quantity(quantity)
        marked_up = print_cost * markup

        unit_price = marked_up + labor
        total = unit_price * quantity

        return CostBreakdown(
            material_cost=material,
            machine_cost=machine,
            labor_cost=labor,
            failure_buffer=failure_buffer,
            print_cost=print_cost,
            markup_multiplier=markup,
            marked_up_print_cost=marked_up,
            unit_price=unit_price,
            quantity=quantity,
            total=total,
        )

    def price_sale(self, sale: Sale) -> Sale:
        """Mutates ``sale`` in place, populating each item's breakdown. Returns
        the same instance for chaining."""
        for item in sale.items:
            item.breakdown = self.price_item(item.spec, item.quantity)
        return sale
