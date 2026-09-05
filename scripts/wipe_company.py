#!/usr/bin/env python3
"""Wipe de una company (p. ej. demo ficticia antes del piloto). DESTRUCTIVO.

Uso:
    uv run --project apps/api python scripts/wipe_company.py --company company_001
    uv run --project apps/api python scripts/wipe_company.py --company company_001 --confirm

Sin --confirm solo muestra el plan (dry-run). Con --confirm borra en orden
FK y verifica conteo cero. Requiere SUPABASE_URL/KEY en .env.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps" / "api"))

from app.db import get_supabase  # noqa: E402

TABLAS = [
    "collection_actions",
    "loan_applications",
    "messages",
    "conversations",
    "alerts",
    "financial_snapshots",
    "transaction_cfdi_matches",
    "accounts_receivable",
    "customer_contacts",
    "transactions",
    "cfdis",
    "bank_accounts",
    "business_profiles",
    "companies",
]


def counts(sb, company: str) -> dict:
    out = {}
    cids = [c["id"] for c in
            sb.table("conversations").select("id")
            .eq("company_id", company).execute().data or []]
    for t in TABLAS:
        try:
            if t == "messages":
                n = 0
                for cid in cids:
                    r = sb.table("messages").select("id", count="exact") \
                        .eq("conversation_id", cid).limit(0).execute()
                    n += r.count or 0
                out[t] = n
                continue
            col = "id" if t == "companies" else "company_id"
            r = sb.table(t).select(col, count="exact").eq(col, company).limit(0).execute()
            out[t] = r.count or 0
        except Exception as e:
            out[t] = f"ERR {e}"[:60]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", required=True)
    ap.add_argument("--confirm", action="store_true")
    args = ap.parse_args()
    sb = get_supabase()
    if sb is None:
        sys.exit("Sin Supabase en .env")
    antes = counts(sb, args.company)
    print(f"company={args.company}")
    for t, n in antes.items():
        print(f"  {t}: {n}")
    if not args.confirm:
        print("dry-run: agrega --confirm para borrar de verdad")
        return
    for t in TABLAS:
        if t == "messages":
            cids = [c["id"] for c in
                    sb.table("conversations").select("id")
                    .eq("company_id", args.company).execute().data or []]
            if args.confirm:
                for cid in cids:
                    sb.table("messages").delete().eq("conversation_id", cid).execute()
            continue
        col = "id" if t == "companies" else "company_id"
        if args.confirm:
            sb.table(t).delete().eq(col, args.company).execute()
    despues = counts(sb, args.company)
    assert all(v == 0 for v in despues.values()), despues
    print("wipe OK: todo en cero")


if __name__ == "__main__":
    main()
