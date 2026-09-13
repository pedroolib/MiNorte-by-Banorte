#!/usr/bin/env python3
"""Piloto TDC: XLSX real -> CSV espejo privado (sin anonimizar, sin commitear).

Uso:
    uv run --project apps/api python scripts/build_pilot_tdc.py \
      --xlsx "seed/private/piloto/BBVA TDC 6159 MOV JULIO 2026.xlsx" \
      --cuenta acc_tdc_001 --company company_pilot --year 2026 --month 7 \
      --chequera-csv seed/private/piloto/transactions_jul2026.csv \
      --out seed/private/piloto/transactions_tdc_jul2026.csv

Valida estructura (49 movs, signos, mes) + cross-check: los 5 abonos
INTERN.PAGO TDC deben existir como PAGO TARJETA en la chequera (misma
referencia CVE). Los datos reales JAMÁS salen de seed/private/.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps" / "api"))

from app.integrations.banking import banorte_tdc_xlsx as tdc  # noqa: E402


def _cve(desc: str) -> str | None:
    m = re.match(r"^(\d+)INTERN\.PAGO TDC$", desc.strip())
    return m.group(1) if m else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", required=True)
    ap.add_argument("--cuenta", required=True)
    ap.add_argument("--company", required=True)
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--month", type=int, required=True)
    ap.add_argument("--chequera-csv", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    movs = tdc.parsear_xlsx(args.xlsx, args.year)
    rep = tdc.validar(movs, args.year, args.month)
    assert rep["n"] == 48, f"se esperaban 48 movs, hay {rep['n']}"
    print(f"movs={rep['n']} compras={rep['compras']} "
          f"abonos={rep['abonos']} anualidad={rep['anualidad']}")

    # cross-check: cada abono existe en chequera como PAGO TARJETA (misma CVE)
    with open(args.chequera_csv, newline="", encoding="utf-8") as f:
        cheq = list(csv.DictReader(f))
    cves_cheq = {}
    for r in cheq:
        if r["categoria"] == "pago_tdc":
            m = re.search(r"(\d{10})", r["descripcion"])
            if m:
                cves_cheq[m.group(1)] = Decimal(r["retiro"])
    pendientes = []
    for m in movs:
        cve = _cve(m.descripcion)
        if cve and m.tipo_mov == "Ingresos en efectivo":
            if cve not in cves_cheq:
                pendientes.append((m.descripcion, str(-m.importe), "SIN par en chequera"))
            elif cves_cheq[cve] != -m.importe:
                pendientes.append((m.descripcion, str(-m.importe),
                                   f"monto difiere: chequera {cves_cheq[cve]}"))
    assert not pendientes, f"abonos sin par exacto: {pendientes}"
    print(f"cross-check: {sum(1 for m in movs if _cve(m.descripcion))} abonos "
          f"con par exacto en chequera")

    filas = [tdc.a_csv_row(m, i + 1, args.company, args.cuenta)
             for i, m in enumerate(movs)]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)
    print(f"escrito {out} ({len(filas)} filas)")


if __name__ == "__main__":
    main()
