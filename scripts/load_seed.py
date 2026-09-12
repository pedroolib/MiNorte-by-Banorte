#!/usr/bin/env python3
"""Carga el seed a Supabase (idempotente: upsert por PK, re-corrible).

Uso:
    uv run --project apps/api python scripts/load_seed.py

Requiere: SUPABASE_URL + SUPABASE_ANON_KEY en .env y haber corrido
apps/api/migrations/001_core.sql en el SQL Editor de Supabase.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps" / "api"))

from app.config import get_settings  # noqa: E402
from app.db import get_supabase  # noqa: E402
from app.integrations.banking.banorte_csv import cargar_csv  # noqa: E402
from app.integrations.sat import cfdi_xml as cx  # noqa: E402
from app.repositories import transactions_repo as repo  # noqa: E402
from app.repositories import cfdi_repo, collections_repo as colrepo  # noqa: E402

# Flujo neto esperado por mes (depósitos - retiros del resumen;
# las devoluciones viajan como ingreso neto, el neto no miente).
ESPERADO_NETO = {
    (2026, 6): "-11876.58",
    (2026, 7): "-13941.40",
    (2026, 8): "-8437.28",
}


def main() -> None:
    s = get_settings()
    sb = get_supabase()
    if sb is None:
        sys.exit("Sin Supabase: pon SUPABASE_URL y SUPABASE_ANON_KEY en .env")

    company_id = s.COMPANY_ID
    try:
        # 1. company + accounts
        company = json.loads((REPO / "seed" / "company.json").read_text())
        repo.upsert_company(sb, {
            "id": company["company_id"],
            "rfc": company["rfc"],
            "razon_social": company["razon_social"],
            "nombre_comercial": company.get("nombre_comercial"),
            "moneda": company.get("moneda", "MXN"),
            "timezone": company.get("timezone", "America/Mexico_City"),
        })
        for acc in json.loads((REPO / "seed" / "accounts.json").read_text()):
            repo.upsert_account(sb, {
                "company_id": company_id,
                "id": acc["account_id"],
                "alias": acc["alias"],
                "clabe": acc.get("clabe"),
                "moneda": acc.get("moneda", "MXN"),
            })
        # 2. transactions (473)
        txns = cargar_csv(REPO / "seed" / "transactions.csv", company_id=company_id)
        n = repo.upsert_transactions(sb, txns)
        print(f"upsert companies=1 accounts=2 transactions={n}")
    except Exception as e:
        if "PGRST205" in str(e) or "Could not find the table" in str(e):
            sys.exit(
                "Tablas no existen en Supabase.\n"
                "Corre apps/api/migrations/001_core.sql en:\n"
                "Supabase Dashboard → SQL Editor → New query → Run"
            )
        raise

    # 3. verificación: conteo + sumas mensuales desde la DB
    assert repo.count(sb, company_id) == len(txns), "conteo distinto al CSV"
    got = repo.fetch_ordered(sb, company_id)
    assert len(got) == len(txns)
    por_mes: dict[tuple[int, int], list] = defaultdict(list)
    for t in got:
        por_mes[(t.date.year, t.date.month)].append(t)
    for (anio, mes), neto_e in ESPERADO_NETO.items():
        fm = por_mes[(anio, mes)]
        neto = sum(
            (t.amount if t.type == "ingreso" else -t.amount for t in fm),
            Decimal("0"),
        )
        assert str(neto) == neto_e, (mes, neto, neto_e)
        print(f"mes {mes}: n={len(fm)} neto={neto} OK")

    # 4. cfdis (XMLs -> parseo real -> upsert)
    cfdi_dir = REPO / "seed" / "cfdis"
    xmls = sorted(cfdi_dir.rglob("*.xml"))
    assert xmls, "sin XMLs: corre scripts/build_seed_cfdis.py"
    cfdis = [cx.parsear_archivo(p, company_id, company["rfc"], base=cfdi_dir)
             for p in xmls]
    n_cfdi = cfdi_repo.upsert_cfdis(sb, cfdis)
    n_emi = sum(1 for c in cfdis if c.tipo == "emitido")
    print(f"upsert cfdis={n_cfdi} (emitidos={n_emi} recibidos={n_cfdi - n_emi})")
    assert cfdi_repo.count(sb, company_id, "emitido") == n_emi
    assert cfdi_repo.count(sb, company_id, "recibido") == n_cfdi - n_emi

    # 5. directorio esqueleto: receptores de emitidos con email NULL,
    # salvo override en seed/private/contacts.json {RFC: {email, phone}}
    # (PII local, nunca en git: alta manual o importación lo llenan).
    vistos: dict[str, str] = {}
    for c in cfdis:
        if c.tipo == "emitido":
            vistos.setdefault(c.receptor_rfc, c.receptor_nombre)
    extra = {}
    priv = REPO / "seed" / "private" / "contacts.json"
    if priv.exists():
        extra = json.loads(priv.read_text())
        print(f"override contactos desde {priv}")
    n_con = colrepo.seed_skeleton(sb, company_id, [
        {"customer_rfc": rfc, "customer_name": nom,
         "email": (extra.get(rfc) or {}).get("email", ""),
         "phone": (extra.get(rfc) or {}).get("phone", "")}
        for rfc, nom in vistos.items()])
    print(f"contactos={n_con} (con email: "
          f"{sum(1 for r in (extra or {}) if (extra[r] or {}).get('email'))})")
    print("load_seed OK")


if __name__ == "__main__":
    main()
