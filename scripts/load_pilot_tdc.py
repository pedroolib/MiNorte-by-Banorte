#!/usr/bin/env python3
"""Carga TDC piloto a Supabase: cuenta acc_tdc_001 + 48 movimientos.

Solo toca company_pilot/acc_tdc_001 (upsert por PK, idempotente).
No verifica conteos globales: la compañía ya tiene la chequera cargada.

Uso:
    uv run --project apps/api python scripts/load_pilot_tdc.py \
      --csv seed/private/piloto/transactions_tdc_jul2026.csv \
      --company company_pilot --cuenta acc_tdc_001 \
      --alias "TDC Banorte 6159" --expect-compras 104967.85 --expect-abonos 114860.63
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps" / "api"))

from app.config import get_settings  # noqa: E402
from app.db import get_supabase  # noqa: E402
from app.integrations.banking.banorte_csv import cargar_csv  # noqa: E402
from app.repositories import transactions_repo as repo  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--company", required=True)
    ap.add_argument("--cuenta", required=True)
    ap.add_argument("--alias", required=True)
    ap.add_argument("--expect-compras", required=True)
    ap.add_argument("--expect-abonos", required=True)
    args = ap.parse_args()

    s = get_settings()
    sb = get_supabase()
    if sb is None:
        sys.exit("Sin Supabase: pon SUPABASE_URL y SUPABASE_ANON_KEY en .env")
    company_id = args.company or s.COMPANY_ID

    repo.upsert_account(sb, {
        "company_id": company_id, "id": args.cuenta,
        "alias": args.alias, "clabe": None, "moneda": "MXN",
    })
    txns = cargar_csv(Path(args.csv), company_id=company_id)
    assert all(t.account_id == args.cuenta for t in txns), "cuenta distinta en CSV"
    n = repo.upsert_transactions(sb, txns)
    got = repo.fetch_ordered(sb, company_id)
    mias = [t for t in got if t.account_id == args.cuenta]
    assert len(mias) == len(txns) == 48, (len(mias), len(txns))
    compras = sum((t.amount for t in mias if t.type == "egreso"), Decimal("0"))
    abonos = sum((t.amount for t in mias if t.type == "ingreso"), Decimal("0"))
    assert str(compras) == args.expect_compras, (compras, args.expect_compras)
    assert str(abonos) == args.expect_abonos, (abonos, args.expect_abonos)
    print(f"cuenta {args.cuenta}: {n} movs "
          f"(compras={compras} abonos={abonos}) OK")
    print("load_pilot_tdc OK")


if __name__ == "__main__":
    main()
