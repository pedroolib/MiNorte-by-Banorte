#!/usr/bin/env python3
"""Carga seed a Supabase (idempotente: upsert por PK, re-corrible).

Uso demo (defaults):
    uv run --project apps/api python scripts/load_seed.py

Uso piloto (datos reales en seed/private/, jamás en git):
    uv run --project apps/api python scripts/load_seed.py \
      --company company_pilot \
      --company-json seed/private/piloto/IDENTIDAD.json \
      --accounts-json seed/private/piloto/IDENTIDAD.json \
      --csv seed/private/piloto/transactions_jul2026.csv \
      --cfdis-dir seed/private/piloto/cfdis \
      --profile-json seed/private/piloto/IDENTIDAD.json \
      --expect seed/private/piloto/esperado.json

Requiere: SUPABASE_URL + SUPABASE_ANON_KEY en .env y migraciones aplicadas.
"""

from __future__ import annotations

import argparse
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
from app.repositories import profile_repo  # noqa: E402

# Flujo neto esperado demo (dev stages). Piloto usa --expect.
ESPERADO_NETO = {
    (2026, 6): "-11876.58",
    (2026, 7): "-13941.40",
    (2026, 8): "-8437.28",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", default=None)
    ap.add_argument("--company-json", default="seed/company.json")
    ap.add_argument("--accounts-json", default="seed/accounts.json")
    ap.add_argument("--csv", default="seed/transactions.csv")
    ap.add_argument("--cfdis-dir", default="seed/cfdis")
    ap.add_argument("--profile-json", default=None,
                    help="IDENTIDAD con giro/ciudad/cp/notas ( privately )")
    ap.add_argument("--expect", default=None,
                    help="JSON {neto: {'YYYY-MM': '...'}} para validar totales")
    args = ap.parse_args()

    s = get_settings()
    sb = get_supabase()
    if sb is None:
        sys.exit("Sin Supabase: pon SUPABASE_URL y SUPABASE_ANON_KEY en .env")

    company_id = args.company or s.COMPANY_ID
    base = REPO
    company = json.loads((base / args.company_json).read_text())
    if "company" in company:  # formato IDENTIDAD piloto
        company = company["company"]
    accounts = json.loads((base / args.accounts_json).read_text())
    if isinstance(accounts, dict) and "accounts" in accounts:
        accounts = accounts["accounts"]
    try:
        # 1. company + accounts
        repo.upsert_company(sb, {
            "id": company["company_id"],
            "rfc": company["rfc"],
            "razon_social": company["razon_social"],
            "nombre_comercial": company.get("nombre_comercial"),
            "moneda": company.get("moneda", "MXN"),
            "timezone": company.get("timezone", "America/Mexico_City"),
        })
        for acc in accounts:
            repo.upsert_account(sb, {
                "company_id": company_id,
                "id": acc["account_id"],
                "alias": acc["alias"],
                "clabe": acc.get("clabe"),
                "moneda": acc.get("moneda", "MXN"),
            })
        # 2. transactions
        txns = cargar_csv(base / args.csv, company_id=company_id)
        n = repo.upsert_transactions(sb, txns)
        print(f"upsert companies=1 accounts={len(accounts)} transactions={n}")
    except Exception as e:
        if "PGRST205" in str(e) or "Could not find the table" in str(e):
            sys.exit("Tablas no existen en Supabase (corre migraciones 001-008).")
        raise

    # 3. verificación: conteo + netos mensuales desde la DB
    # (>= porque el piloto carga por meses acumulativos; el neto por mes
    # es la guarda exacta)
    assert repo.count(sb, company_id) >= len(txns), "faltan txns en DB"
    got = repo.fetch_ordered(sb, company_id)
    en_db = {t.id for t in got}
    assert all(t.id in en_db for t in txns), "faltan ids del CSV en DB"
    if args.expect:
        esperado = {(int(k[:4]), int(k[5:7])): v
                    for k, v in json.loads(Path(args.expect).read_text())["neto"].items()}
    else:
        esperado = ESPERADO_NETO
    por_mes: dict[tuple[int, int], list] = defaultdict(list)
    for t in got:
        por_mes[(t.date.year, t.date.month)].append(t)
    for (anio, mes), neto_e in esperado.items():
        fm = por_mes[(anio, mes)]
        neto = sum(
            (t.amount if t.type == "ingreso" else -t.amount for t in fm),
            Decimal("0"),
        )
        assert str(neto) == neto_e, (mes, neto, neto_e)
        print(f"mes {mes}: n={len(fm)} neto={neto} OK")

    # 4. cfdis (XMLs -> parseo real -> upsert)
    cfdi_dir = base / args.cfdis_dir
    xmls = sorted(cfdi_dir.rglob("*.xml"))
    assert xmls, f"sin XMLs en {cfdi_dir}"
    cfdis = [cx.parsear_archivo(p, company_id, company["rfc"], base=cfdi_dir)
             for p in xmls]
    n_cfdi = cfdi_repo.upsert_cfdis(sb, cfdis)
    n_emi = sum(1 for c in cfdis if c.tipo == "emitido")
    print(f"upsert cfdis={n_cfdi} (emitidos={n_emi} recibidos={n_cfdi - n_emi})")
    # >= por cargas piloto acumulativas (julio + febrero conviven)
    assert cfdi_repo.count(sb, company_id, "emitido") >= n_emi
    assert cfdi_repo.count(sb, company_id, "recibido") >= n_cfdi - n_emi

    # 5. directorio esqueleto (clave RFC+nombre: XAXX compartido en piloto).
    # Sin email salvo override seed/private/contacts.json (PII local).
    vistos: dict[tuple[str, str], str] = {}
    for c in cfdis:
        if c.tipo == "emitido":
            vistos.setdefault((c.receptor_rfc, c.receptor_nombre), c.receptor_nombre)
    extra = {}
    priv = REPO / "seed" / "private" / "contacts.json"
    if priv.exists():
        extra = json.loads(priv.read_text())
        print(f"override contactos desde {priv}")
    n_con = colrepo.seed_skeleton(sb, company_id, [
        {"customer_rfc": rfc, "customer_name": nom,
         "email": (extra.get(f"{rfc}|{nom}") or {}).get("email", ""),
         "phone": (extra.get(f"{rfc}|{nom}") or {}).get("phone", "")}
        for (rfc, nom) in vistos])
    print(f"contactos={n_con}")

    # 6. perfil: archivo si se da, si no detección; nunca pisa existente.
    try:
        if profile_repo.get_profile(sb, company_id) is None:
            if args.profile_json:
                ident = json.loads((base / args.profile_json).read_text())
                prof = ident.get("profile", {})
                sug = profile_repo.sugerir_perfil(txns, cfdis)
                fila = {
                    "company_id": company_id,
                    "giro": prof.get("giro") or sug["giro"],
                    "ciudad": prof.get("ciudad") or sug["ciudad"],
                    "estado": prof.get("estado") or sug["estado"],
                    "cp": prof.get("cp") or sug["cp"],
                    "tamanio": prof.get("tamanio") or sug["tamanio"],
                    "modelo": prof.get("modelo") or sug["modelo"],
                    "notas": prof.get("notas", "")}
                sb.table("business_profiles").insert(fila).execute()
                print(f"perfil creado desde {args.profile_json}: "
                      f"{fila['giro']} · {fila['ciudad']}")
            else:
                sug = profile_repo.sugerir_perfil(txns, cfdis)
                sb.table("business_profiles").insert({
                    "company_id": company_id, "giro": sug["giro"],
                    "ciudad": sug["ciudad"], "estado": sug["estado"],
                    "cp": sug["cp"], "tamanio": sug["tamanio"],
                    "modelo": sug["modelo"], "notas": "seed inicial"}).execute()
                print(f"perfil default creado: {sug['giro']} · "
                      f"{sug['ciudad']} · {sug['tamanio']} · {sug['modelo']}")
        else:
            print("perfil existente: se respeta")
    except Exception as e:
        print(f"perfil omitido ({e})")
    print("load_seed OK")


if __name__ == "__main__":
    main()
