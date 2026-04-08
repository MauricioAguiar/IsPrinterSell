"""Rich domain entities. These are framework-agnostic Python dataclasses."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from .value_objects import CostBreakdown, Money, SaleStatus


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


@dataclass
class Client:
    name: str
    phone_e164: str  # e.g. "+5511999999999" — required for WhatsApp
    id: Optional[int] = None
    email: Optional[str] = None
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Client name is required.")
        if not self.phone_e164.startswith("+"):
            raise ValueError(
                "Client phone must be E.164 format, e.g. +5511999999999."
            )


# ---------------------------------------------------------------------------
# Print job spec — pricing inputs for a single line item
# ---------------------------------------------------------------------------


@dataclass
class PrintSpec:
    """Everything the pricing engine needs to cost a single printed item."""

    filament_grams: Decimal
    print_hours: Decimal
    customization_hours: Decimal = Decimal("0")
    painting_hours: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        for name, value in (
            ("filament_grams", self.filament_grams),
            ("print_hours", self.print_hours),
            ("customization_hours", self.customization_hours),
            ("painting_hours", self.painting_hours),
        ):
            if not isinstance(value, Decimal):
                object.__setattr__(self, name, Decimal(str(value)))
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be >= 0")


# ---------------------------------------------------------------------------
# Sale aggregate
# ---------------------------------------------------------------------------


@dataclass
class SaleItem:
    name: str
    quantity: int
    spec: PrintSpec
    id: Optional[int] = None
    # Populated by the pricing engine before persistence.
    breakdown: Optional[CostBreakdown] = None

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("SaleItem.quantity must be > 0.")
        if not self.name.strip():
            raise ValueError("SaleItem.name is required.")

    @property
    def line_total(self) -> Money:
        if self.breakdown is None:
            raise RuntimeError(
                "SaleItem has no cost breakdown yet — run the pricing engine first."
            )
        return self.breakdown.total


@dataclass
class Sale:
    client_id: int
    items: list[SaleItem]
    id: Optional[int] = None
    status: SaleStatus = SaleStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    due_date: Optional[date] = None
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.items:
            raise ValueError("A Sale needs at least one item.")

    # Aggregates ------------------------------------------------------------
    @property
    def total(self) -> Money:
        total = Money.zero()
        for item in self.items:
            total = total + item.line_total
        return total

    @property
    def total_print_hours(self) -> Decimal:
        return sum(
            (item.spec.print_hours * item.quantity for item in self.items),
            Decimal("0"),
        )

    @property
    def total_material_cost(self) -> Money:
        total = Money.zero()
        for item in self.items:
            if item.breakdown is not None:
                total = total + item.breakdown.material_cost * item.quantity
        return total

    @property
    def total_machine_cost(self) -> Money:
        total = Money.zero()
        for item in self.items:
            if item.breakdown is not None:
                total = total + item.breakdown.machine_cost * item.quantity
        return total

    @property
    def total_labor_cost(self) -> Money:
        total = Money.zero()
        for item in self.items:
            if item.breakdown is not None:
                total = total + item.breakdown.labor_cost * item.quantity
        return total

    @property
    def effective_markup(self) -> Decimal:
        if not self.items or any(i.breakdown is None for i in self.items):
            return Decimal("0")
        # Weighted by quantity — cleaner than picking the first item's markup.
        num = Decimal("0")
        den = Decimal("0")
        for item in self.items:
            assert item.breakdown is not None
            num += item.breakdown.markup_multiplier * item.quantity
            den += item.quantity
        return (num / den).quantize(Decimal("0.01")) if den else Decimal("0")

    # State transitions -----------------------------------------------------
    def mark_ready(self) -> None:
        if self.status in (SaleStatus.DELIVERED, SaleStatus.CANCELLED):
            raise ValueError(f"Cannot mark a {self.status.value} sale as ready.")
        self.status = SaleStatus.READY

    def mark_delivered(self) -> None:
        if self.status != SaleStatus.READY:
            raise ValueError(
                "Only READY sales can be marked as delivered — "
                f"current status: {self.status.value}."
            )
        self.status = SaleStatus.DELIVERED

    def cancel(self) -> None:
        if self.status == SaleStatus.DELIVERED:
            raise ValueError("Delivered sales cannot be cancelled.")
        self.status = SaleStatus.CANCELLED
