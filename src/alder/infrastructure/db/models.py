"""SQLAlchemy 2.0 ORM models.

These are *persistence* models, not domain models. Repositories are
responsible for mapping them to and from ``alder.domain`` entities. Keeping
them separate prevents ORM concerns (eager loading, lazy columns, dirty
tracking) from leaking into the business logic.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    pass


class ClientRow(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone_e164: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True, index=True
    )
    email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    sales: Mapped[List["SaleRow"]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )


class SaleRow(Base):
    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    total_brl: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    client: Mapped[ClientRow] = relationship(back_populates="sales")
    items: Mapped[List["SaleItemRow"]] = relationship(
        back_populates="sale", cascade="all, delete-orphan"
    )


class SaleItemRow(Base):
    __tablename__ = "sale_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sale_id: Mapped[int] = mapped_column(
        ForeignKey("sales.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    # Print spec
    filament_grams: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    print_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    customization_hours: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0")
    )
    painting_hours: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0")
    )

    # Cost breakdown snapshot — preserved for auditing even if constants change.
    material_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    machine_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    labor_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    failure_buffer: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    markup_multiplier: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    sale: Mapped[SaleRow] = relationship(back_populates="items")
