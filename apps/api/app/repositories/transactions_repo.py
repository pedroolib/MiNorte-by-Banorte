"""Repo de transactions sobre Supabase (PostgREST).

Upsert idempotente por (company_id, id): re-correr el loader no duplica.
Lecturas ordenadas por fecha para que la cadena de saldos se mantenga.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from app.schemas.transaction import Transaction


def _row(t: Transaction) -> dict:
    neto = t.amount if t.type == "ingreso" else -t.amount
    return {
        "company_id": t.company_id,
        "id": t.id,
        "account_id": t.account_id,
        "fecha": t.date.isoformat(),
        "descripcion": t.description,
        "comercio": t.merchant_name,
        "rfc": t.merchant_rfc,
        "tipo": t.type,
        "monto": str(abs(neto)),
        "saldo": str(t.balance) if t.balance is not None else None,
        "es_interno": t.es_interno,
        "categoria": t.categoria,
    }


def _to_tx(r: dict) -> Transaction:
    return Transaction(
        id=r["id"],
        company_id=r["company_id"],
        account_id=r["account_id"],
        amount=Decimal(str(r["monto"])),
        currency="MXN",
        date=datetime.fromisoformat(r["fecha"]),
        description=r["descripcion"],
        merchant_name=r.get("comercio") or "DESCONOCIDO",
        merchant_rfc=r.get("rfc"),
        type=r["tipo"],
        balance=Decimal(str(r["saldo"])) if r.get("saldo") is not None else None,
        source="banorte_mock",
        es_interno=bool(r.get("es_interno")),
        categoria=r.get("categoria") or "otro",
    )


def upsert_transactions(sb: Any, txns: list[Transaction], batch: int = 200) -> int:
    n = 0
    for i in range(0, len(txns), batch):
        chunk = [_row(t) for t in txns[i:i + batch]]
        sb.table("transactions").upsert(chunk, on_conflict="company_id,id").execute()
        n += len(chunk)
    return n


def upsert_company(sb: Any, company: dict) -> None:
    sb.table("companies").upsert(company, on_conflict="id").execute()


def upsert_account(sb: Any, account: dict) -> None:
    sb.table("bank_accounts").upsert(account, on_conflict="company_id,id").execute()


def fetch_ordered(sb: Any, company_id: str) -> list[Transaction]:
    # Orden cronológico determinista: los ids son secuenciales en el
    # orden del estado de cuenta (desempata fechas iguales/clamp JUN-30).
    res = (
        sb.table("transactions")
        .select("*")
        .eq("company_id", company_id)
        .order("fecha")
        .order("id")
        .execute()
    )
    return [_to_tx(r) for r in (res.data or [])]


def count(sb: Any, company_id: str) -> int:
    res = (
        sb.table("transactions")
        .select("id", count="exact")
        .eq("company_id", company_id)
        .execute()
    )
    return res.count or 0
