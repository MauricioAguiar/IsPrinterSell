"""SQLAlchemy implementation of SaleRepository.

Maps the ``Sale`` aggregate to ``SaleRow`` + ``SaleItemRow``. The pricing
breakdown is persisted *per line item* so historical prices are preserved
even if business constants change later.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from alder.domain.entities import PrintSpec, Sale, SaleItem
from alder.domain.value_objects import CostBreakdown, Money, SaleStatus
from alder.infrastructure.db.models import SaleItemRow, SaleRow


class SqlAlchemySaleRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    # -- mapping --------------------------------------------------------------
    @staticmethod
    def _item_to_row(item: SaleItem) -> SaleItemRow:
        b = item.breakdown
        if b is None:
            raise RuntimeError(
                "Cannot persist SaleItem without a cost breakdown — "
                "run the PricingEngine first."
            )
        return SaleItemRow(
            id=item.id,
            name=item.name,
            quantity=item.quantity,
            filament_grams=item.spec.filament_grams,
            print_hours=item.spec.print_hours,
            customization_hours=item.spec.customization_hours,
            painting_hours=item.spec.painting_hours,
            material_cost=b.material_cost.amount,
            machine_cost=b.machine_cost.amount,
            labor_cost=b.labor_cost.amount,
            failure_buffer=b.failure_buffer.amount,
            markup_multiplier=b.markup_multiplier,
            unit_price=b.unit_price.amount,
            line_total=b.total.amount,
        )

    @staticmethod
    def _item_to_domain(row: SaleItemRow) -> SaleItem:
        spec = PrintSpec(
            filament_grams=row.filament_grams,
            print_hours=row.print_hours,
            customization_hours=row.customization_hours,
            painting_hours=row.painting_hours,
        )
        breakdown = CostBreakdown(
            material_cost=Money(row.material_cost),
            machine_cost=Money(row.machine_cost),
            labor_cost=Money(row.labor_cost),
            failure_buffer=Money(row.failure_buffer),
            print_cost=Money(
                row.material_cost + row.machine_cost + row.failure_buffer
            ),
            markup_multiplier=row.markup_multiplier,
            marked_up_print_cost=Money(
                row.unit_price - row.labor_cost
            ),
            unit_price=Money(row.unit_price),
            quantity=row.quantity,
            total=Money(row.line_total),
        )
        return SaleItem(
            id=row.id,
            name=row.name,
            quantity=row.quantity,
            spec=spec,
            breakdown=breakdown,
        )

    def _to_domain(self, row: SaleRow) -> Sale:
        return Sale(
            id=row.id,
            client_id=row.client_id,
            status=SaleStatus(row.status),
            created_at=row.created_at,
            due_date=row.due_date,
            notes=row.notes or "",
            items=[self._item_to_domain(i) for i in row.items],
        )

    # -- operations -----------------------------------------------------------
    def add(self, sale: Sale) -> Sale:
        row = SaleRow(
            client_id=sale.client_id,
            status=sale.status.value,
            total_brl=sale.total.amount,
            due_date=sale.due_date,
            notes=sale.notes or "",
            items=[self._item_to_row(i) for i in sale.items],
        )
        self._s.add(row)
        self._s.flush()
        # Propagate generated ids back to the aggregate.
        sale.id = row.id
        for src, dst in zip(row.items, sale.items):
            dst.id = src.id
        return sale

    def get(self, sale_id: int) -> Optional[Sale]:
        stmt = (
            select(SaleRow)
            .where(SaleRow.id == sale_id)
            .options(selectinload(SaleRow.items))
        )
        row = self._s.execute(stmt).scalar_one_or_none()
        return self._to_domain(row) if row else None

    def list(self, *, limit: int = 100, offset: int = 0) -> list[Sale]:
        stmt = (
            select(SaleRow)
            .options(selectinload(SaleRow.items))
            .order_by(SaleRow.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [self._to_domain(r) for r in self._s.execute(stmt).scalars()]

    def update(self, sale: Sale) -> Sale:
        row = self._s.get(SaleRow, sale.id)
        if row is None:
            raise LookupError(f"Sale {sale.id} not found.")
        row.status = sale.status.value
        row.notes = sale.notes or ""
        row.due_date = sale.due_date
        row.total_brl = sale.total.amount if all(
            i.breakdown for i in sale.items
        ) else Decimal("0")
        self._s.flush()
        return sale
