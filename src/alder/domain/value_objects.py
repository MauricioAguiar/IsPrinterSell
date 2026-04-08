"""Immutable value objects used throughout the domain."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum


# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------

_QUANT = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class Money:
    """BRL-denominated monetary amount. Stored with 2-decimal precision.

    We deliberately avoid ``float`` for currency maths. All constructors
    normalise via ``Decimal.quantize`` so equality is deterministic.
    """

    amount: Decimal
    currency: str = "BRL"

    def __post_init__(self) -> None:  # pragma: no cover - trivial
        if not isinstance(self.amount, Decimal):
            object.__setattr__(self, "amount", Decimal(str(self.amount)))
        object.__setattr__(
            self, "amount", self.amount.quantize(_QUANT, rounding=ROUND_HALF_UP)
        )

    # Factories -------------------------------------------------------------
    @classmethod
    def zero(cls) -> "Money":
        return cls(Decimal("0"))

    @classmethod
    def of(cls, value: float | int | str | Decimal) -> "Money":
        return cls(Decimal(str(value)))

    # Arithmetic ------------------------------------------------------------
    def _check(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise ValueError(
                f"Currency mismatch: {self.currency} vs {other.currency}"
            )

    def __add__(self, other: "Money") -> "Money":
        self._check(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._check(other)
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, factor: float | int | Decimal) -> "Money":
        return Money(self.amount * Decimal(str(factor)), self.currency)

    __rmul__ = __mul__

    def __truediv__(self, divisor: float | int | Decimal) -> "Money":
        return Money(self.amount / Decimal(str(divisor)), self.currency)

    def __lt__(self, other: "Money") -> bool:
        self._check(other)
        return self.amount < other.amount

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"R$ {self.amount:.2f}"

    def as_float(self) -> float:
        return float(self.amount)


# ---------------------------------------------------------------------------
# Sale lifecycle
# ---------------------------------------------------------------------------


class SaleStatus(str, Enum):
    PENDING = "pending"
    IN_PRODUCTION = "in_production"
    READY = "ready"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Pricing breakdown
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CostBreakdown:
    """Result of the pricing engine — every component exposed for auditing."""

    material_cost: Money
    machine_cost: Money
    labor_cost: Money
    failure_buffer: Money
    print_cost: Money  # material + machine + failure_buffer
    markup_multiplier: Decimal
    marked_up_print_cost: Money
    unit_price: Money  # what the customer pays per unit
    quantity: int
    total: Money

    @property
    def margin_pct(self) -> Decimal:
        """Gross margin % relative to total price.

        margin = (total - raw_cost) / total
        where raw_cost = (print_cost + labor) * qty
        """
        raw_cost = (self.print_cost + self.labor_cost) * self.quantity
        if self.total.amount == 0:
            return Decimal("0")
        return (
            (self.total.amount - raw_cost.amount) / self.total.amount * Decimal("100")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
