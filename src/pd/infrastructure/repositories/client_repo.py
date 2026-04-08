"""SQLAlchemy implementation of ClientRepository."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from alder.domain.entities import Client
from alder.infrastructure.db.models import ClientRow


class SqlAlchemyClientRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    # -- mapping --------------------------------------------------------------
    @staticmethod
    def _to_domain(row: ClientRow) -> Client:
        return Client(
            id=row.id,
            name=row.name,
            phone_e164=row.phone_e164,
            email=row.email,
            notes=row.notes or "",
        )

    @staticmethod
    def _to_row(client: Client) -> ClientRow:
        return ClientRow(
            id=client.id,
            name=client.name,
            phone_e164=client.phone_e164,
            email=client.email,
            notes=client.notes or "",
        )

    # -- operations -----------------------------------------------------------
    def add(self, client: Client) -> Client:
        row = self._to_row(client)
        self._s.add(row)
        self._s.flush()  # populate id without committing
        return self._to_domain(row)

    def get(self, client_id: int) -> Optional[Client]:
        row = self._s.get(ClientRow, client_id)
        return self._to_domain(row) if row else None

    def get_by_phone(self, phone_e164: str) -> Optional[Client]:
        stmt = select(ClientRow).where(ClientRow.phone_e164 == phone_e164)
        row = self._s.execute(stmt).scalar_one_or_none()
        return self._to_domain(row) if row else None

    def list(self) -> list[Client]:
        stmt = select(ClientRow).order_by(ClientRow.name)
        return [self._to_domain(r) for r in self._s.execute(stmt).scalars()]
