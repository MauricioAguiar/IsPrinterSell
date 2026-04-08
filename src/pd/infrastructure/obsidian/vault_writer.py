"""Writes sale notes into a local Obsidian vault.

* File name:  ``{vault}/{subdir}/SALE-{id:05d}-{client_slug}.md``
* Atomic:     writes to a temp file then ``os.replace`` to avoid Obsidian
              picking up a half-written note.
* Idempotent: re-writing the same sale overwrites the existing note so the
              YAML frontmatter is always current.
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from alder.domain.entities import Client, Sale

log = logging.getLogger(__name__)

_slug_re = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    return _slug_re.sub("-", text.lower()).strip("-") or "unknown"


class ObsidianVaultWriter:
    def __init__(self, vault_root: str | Path, subdir: str = "Sales") -> None:
        self._root = Path(vault_root).expanduser().resolve()
        self._subdir = subdir

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def write_sale_note(self, sale: Sale, client: Client) -> str:
        target_dir = self._root / self._subdir
        target_dir.mkdir(parents=True, exist_ok=True)

        filename = f"SALE-{sale.id:05d}-{_slugify(client.name)}.md"
        target = target_dir / filename

        frontmatter = self._build_frontmatter(sale, client)
        body = self._build_body(sale, client)
        content = f"---\n{yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)}---\n\n{body}\n"

        self._atomic_write(target, content)
        log.info("Wrote Obsidian note for sale %s → %s", sale.id, target)
        return str(target)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    @staticmethod
    def _build_frontmatter(sale: Sale, client: Client) -> dict[str, Any]:
        items = [
            {
                "name": i.name,
                "qty": i.quantity,
                "unit_price": float(i.breakdown.unit_price.amount)
                if i.breakdown
                else None,
            }
            for i in sale.items
        ]
        return {
            "id": f"SALE-{sale.id:05d}",
            "client": client.name,
            "date": sale.created_at.date().isoformat()
            if isinstance(sale.created_at, datetime)
            else str(sale.created_at),
            "status": sale.status.value,
            "total_brl": float(sale.total.amount),
            "material_cost": float(sale.total_material_cost.amount),
            "machine_cost": float(sale.total_machine_cost.amount),
            "labor_cost": float(sale.total_labor_cost.amount),
            "markup": float(sale.effective_markup),
            "margin_pct": float(sale.items[0].breakdown.margin_pct)
            if sale.items and sale.items[0].breakdown
            else 0.0,
            "items": items,
            "tags": ["sale", "3dprint"],
        }

    @staticmethod
    def _build_body(sale: Sale, client: Client) -> str:
        lines = [
            f"# Sale {sale.id} — {client.name}",
            "",
            f"- **Phone:** {client.phone_e164}",
            f"- **Status:** {sale.status.value}",
            f"- **Total:** {sale.total}",
            "",
            "## Items",
            "",
            "| Item | Qty | Unit Price | Line Total |",
            "|------|----:|-----------:|-----------:|",
        ]
        for i in sale.items:
            if i.breakdown is None:
                continue
            lines.append(
                f"| {i.name} | {i.quantity} | {i.breakdown.unit_price} | {i.breakdown.total} |"
            )
        if sale.notes:
            lines += ["", "## Notes", "", sale.notes]
        return "\n".join(lines)

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        # tempfile in the same directory so os.replace is atomic on the same FS.
        fd, tmp_path = tempfile.mkstemp(
            prefix=".alder-", suffix=".md.tmp", dir=str(path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path, path)
        except Exception:
            # Clean up the stray temp file on any failure.
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
