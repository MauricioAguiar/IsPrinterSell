"""One-shot Excel -> SQLite ETL.

The legacy spreadsheet is assumed to have at least:

    client_name | client_phone | item_name | quantity | filament_grams |
    print_hours | customization_hours | painting_hours | date | status

Column names are matched case-insensitively; missing optional fields default
to zero/pending. Rows with the same ``client_phone`` are grouped into one
client; rows sharing (client_phone, date) are grouped into one sale.

Usage::

    python -m alder.infrastructure.etl.excel_importer ./legacy.xlsx --sheet Sales
"""
from __future__ import annotations

import argparse
import logging
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from alder.application.services.pricing import PricingEngine
from alder.domain.entities import Client, PrintSpec, Sale, SaleItem
from alder.domain.value_objects import SaleStatus
from alder.infrastructure.db.session import init_schema
from alder.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Column aliases — normalises messy legacy spreadsheets.
# ---------------------------------------------------------------------------

_ALIASES = {
    "client_name": {"client", "client_name", "cliente", "nome"},
    "client_phone": {"phone", "client_phone", "telefone", "whatsapp"},
    "item_name": {"item", "item_name", "produto", "product"},
    "quantity": {"qty", "quantity", "quantidade"},
    "filament_grams": {"grams", "filament_grams", "gramas", "filamento"},
    "print_hours": {"print_hours", "horas", "tempo_impressao"},
    "customization_hours": {"customization_hours", "custom_hours", "custom"},
    "painting_hours": {"painting_hours", "paint_hours", "pintura"},
    "date": {"date", "data"},
    "status": {"status"},
}


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename: dict[str, str] = {}
    lower = {c.lower().strip(): c for c in df.columns}
    for canonical, aliases in _ALIASES.items():
        for alias in aliases:
            if alias in lower:
                rename[lower[alias]] = canonical
                break
    return df.rename(columns=rename)


def _dec(value: Any, default: str = "0") -> Decimal:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return Decimal(default)
    return Decimal(str(value))


def _phone(raw: Any) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    # Heuristic: if user hasn't prefixed '+', assume Brazil (+55).
    if not s.startswith("+"):
        s = "+55" + "".join(ch for ch in s if ch.isdigit())
    return s


# ---------------------------------------------------------------------------
# Importer
# ---------------------------------------------------------------------------


def import_excel(path: Path, *, sheet: str | int = 0) -> dict[str, int]:
    df = pd.read_excel(path, sheet_name=sheet)
    df = _normalise_columns(df)

    required = {"client_name", "client_phone", "item_name", "quantity",
                "filament_grams", "print_hours"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    init_schema()
    pricing = PricingEngine()

    clients_created = 0
    sales_created = 0

    # Group legacy rows: (phone, date) -> one sale.
    group_cols = ["client_phone", "date"] if "date" in df.columns else ["client_phone"]
    for keys, group in df.groupby(group_cols, dropna=False):
        first = group.iloc[0]
        phone = _phone(first["client_phone"])
        if not phone:
            log.warning("Skipping row group %s — empty phone", keys)
            continue
        name = str(first["client_name"]).strip() or "Unknown"

        items = [
            SaleItem(
                name=str(r["item_name"]).strip() or "Item",
                quantity=int(r["quantity"]),
                spec=PrintSpec(
                    filament_grams=_dec(r["filament_grams"]),
                    print_hours=_dec(r["print_hours"]),
                    customization_hours=_dec(
                        r.get("customization_hours") if "customization_hours" in r else 0
                    ),
                    painting_hours=_dec(
                        r.get("painting_hours") if "painting_hours" in r else 0
                    ),
                ),
            )
            for _, r in group.iterrows()
        ]

        status_raw = str(first.get("status", "pending")).lower().strip() if "status" in first else "pending"
        try:
            status = SaleStatus(status_raw)
        except ValueError:
            status = SaleStatus.PENDING

        with SqlAlchemyUnitOfWork() as uow:
            client = uow.clients.get_by_phone(phone)
            if client is None:
                client = uow.clients.add(
                    Client(name=name, phone_e164=phone)
                )
                clients_created += 1
            sale = Sale(client_id=client.id, items=items, status=status)  # type: ignore[arg-type]
            pricing.price_sale(sale)
            uow.sales.add(sale)
            uow.commit()
            sales_created += 1

    summary = {"clients_created": clients_created, "sales_created": sales_created}
    log.info("ETL done: %s", summary)
    return summary


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description="Import legacy Excel sales sheet into Alder.")
    parser.add_argument("path", type=Path)
    parser.add_argument("--sheet", default=0)
    args = parser.parse_args(argv)

    if not args.path.exists():
        print(f"File not found: {args.path}", file=sys.stderr)
        return 2
    summary = import_excel(args.path, sheet=args.sheet)
    print(summary)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
