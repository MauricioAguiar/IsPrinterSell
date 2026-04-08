"""Domain events. Handlers subscribe to these via the application event bus."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """Marker base class — every event carries a UTC timestamp."""

    name: ClassVar[str] = "domain_event"


@dataclass(frozen=True, slots=True)
class SaleRegistered(DomainEvent):
    name: ClassVar[str] = "sale_registered"
    sale_id: int
    client_id: int
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class OrderReady(DomainEvent):
    name: ClassVar[str] = "order_ready"
    sale_id: int
    client_id: int
    occurred_at: datetime
