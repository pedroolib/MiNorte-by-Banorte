#!/usr/bin/env python3
"""Enmascara corridas de dígitos en descripciones (privado).

- Corridas de >=10 dígitos -> '*' conservando últimos 4.
  Cubre CLABE (18), tarjetas (16), cuentas (10-11), refs SPEI (12+) y
  el CVE de INTERN.PAGO TDC (el cross-check TDC<->chequera corre sobre
  los CSVs CRUDOS, antes de este paso).
- SOLO toca `descripcion`. Comercio, montos, fechas, categorías, RFCs:
  intactos (el análisis no usa dígitos de descripcion: clasificar_bbva
  es por keywords; reconcile usa merchant_name; signals usa montos).
- Idempotente: sobre texto ya enmascarado no cambia nada.

Uso:
    uv run --project apps/api python scripts/enmascarar_cuentas.py
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PILOTO = REPO / "seed" / "private" / "piloto"

PAT = re.compile(r"\d{10,}")


def enmascara(texto: str) -> str:
    return PAT.sub(lambda m: "*" * (len(m.group(0)) - 4) + m.group(0)[-4:],
                   texto)


def main() -> None:
    archivos = sorted(PILOTO.glob("transactions_final_*.csv"))
    assert archivos, "sin CSVs finales"
    for dst in archivos:
        rows = list(csv.DictReader(open(dst, encoding="utf-8")))
        n = 0
        for r in rows:
            nueva = enmascara(r["descripcion"])
            if nueva != r["descripcion"]:
                n += 1
            r["descripcion"] = nueva
        with open(dst, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"{dst.name}: {n}/{len(rows)} descripciones enmascaradas")


if __name__ == "__main__":
    main()
