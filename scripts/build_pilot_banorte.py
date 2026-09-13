#!/usr/bin/env python3
"""Piloto Banorte: PDF real -> CSV espejo privado (sin anonimizar, sin commitear).

Uso:
    uv run --project apps/api python scripts/build_pilot_banorte.py \
      --pdf "seed/private/piloto/chequera_jul2026.pdf" \
      --cuenta acc_banorte_001 --company company_pilot --year 2026 \
      --saldo-inicial 463711.92 --out seed/private/piloto/transactions_jul2026.csv \
      [--expect seed/private/piloto/esperado.json]

Valida cadena de saldos + totales (falla si el layout cambió). Los datos
reales JAMÁS salen de seed/private/ ni entran a git.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps" / "api"))

from app.integrations.banking import banorte_comercial_pdf as bcom  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--cuenta", required=True)
    ap.add_argument("--company", required=True)
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--saldo-inicial", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--expect", default=None,
                    help="JSON {dep, ret, final} para validar totales")
    args = ap.parse_args()

    movs = bcom.parsear_texto(bcom.extraer_texto(Path(args.pdf)), args.year)
    errs, final = bcom.validar_cadena(movs, Decimal(args.saldo_inicial))
    assert not errs, errs[:10]
    dep, ret = bcom.totales(movs)
    if args.expect:
        esp = json.loads(Path(args.expect).read_text())
        assert str(dep) == esp["dep"], (dep, esp["dep"])
        assert str(ret) == esp["ret"], (ret, esp["ret"])
        assert str(final) == esp["final"], (final, esp["final"])
        print(f"totales OK vs esperado: dep={dep} ret={ret} final={final}")
    else:
        print(f"dep={dep} ret={ret} final={final} (verificar contra resumen)")

    from collections import Counter
    cats: Counter = Counter()
    filas = []
    seq = 0
    for m in movs:
        cat, interno = bcom.clasificar_banorte(m.descripcion)
        cats[cat] += 1
        seq += 1
        filas.append({
            "id": f"txn_pilot{seq:04d}",
            "company_id": args.company,
            "account_id": args.cuenta,
            "fecha": f"{m.fecha_oper.isoformat()}T12:00:00-06:00",
            "descripcion": m.descripcion,
            "comercio": m.comercio or "DESCONOCIDO",
            "rfc": "",
            "tipo": "ingreso" if m.deposito > 0 else "egreso",
            "deposito": str(m.deposito),
            "retiro": str(m.retiro),
            "saldo": str(m.saldo),
            "es_interno": "1" if interno else "0",
            "categoria": cat,
            "source": "banorte_mock",
        })
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)
    print(f"escrito {out} ({len(filas)} filas)")
    for k, v in sorted(cats.items()):
        print(f"  {v:4d} {k}")


if __name__ == "__main__":
    main()
