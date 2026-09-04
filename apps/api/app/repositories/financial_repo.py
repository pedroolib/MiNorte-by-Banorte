"""Repo de resultados financieros: matches, CxC, snapshots, alertas."""

from typing import Any

from app.schemas.match import Match
from app.schemas.receivable import Receivable


def upsert_matches(sb: Any, company_id: str, matches: list[Match]) -> int:
    rows = [{
        "company_id": company_id, "transaction_id": m.transaction_id,
        "cfdi_uuid": m.cfdi_id, "score": str(m.score),
        "amount_score": str(m.amount_score), "date_score": str(m.date_score),
        "merchant_score": str(m.merchant_score), "status": m.status,
    } for m in matches]
    for i in range(0, len(rows), 200):
        sb.table("transaction_cfdi_matches").upsert(
            rows[i:i + 200], on_conflict="company_id,transaction_id").execute()
    return len(rows)


def upsert_receivables(sb: Any, recs: list[Receivable]) -> int:
    rows = [{
        "id": r.id, "company_id": r.company_id, "cfdi_id": r.cfdi_id,
        "customer_name": r.customer_name, "customer_rfc": r.customer_rfc,
        "amount": str(r.amount), "amount_paid": str(r.amount_paid),
        "amount_pending": str(r.amount_pending or r.amount - r.amount_paid),
        "issued_at": r.issued_at.isoformat(),
        "due_date": r.due_date.isoformat() if r.due_date else None,
        "status": r.status,
    } for r in recs]
    for i in range(0, len(rows), 200):
        sb.table("accounts_receivable").upsert(
            rows[i:i + 200], on_conflict="company_id,id").execute()
    return len(rows)


def upsert_snapshot(sb: Any, company_id: str, month: str, snap: dict) -> None:
    sb.table("financial_snapshots").upsert({
        "company_id": company_id, "month": month,
        "ventas": str(snap["ventas"]), "gastos": str(snap["gastos"]),
        "utilidad": str(snap["utilidad"]), "margen": str(snap["margen"]),
        "efectivo": str(snap["efectivo"]),
        "impuesto_estimado": str(snap["impuesto_estimado"]),
        "cxc_total": str(snap["cxc_total"]), "flujo_neto": str(snap["flujo_neto"]),
        "sin_cfdi_count": snap.get("sin_cfdi_count", 0),
        "sin_cfdi_total": str(snap.get("sin_cfdi_total", 0)),
        "payload": snap.get("payload", {}),
    }, on_conflict="company_id,month").execute()


def upsert_alerts(sb: Any, alertas: list[dict]) -> int:
    rows = [{
        "id": a["id"], "company_id": a["company_id"], "month": a["month"],
        "rule": a["rule"], "severity": a["severity"], "titulo": a["titulo"],
        "detalle": a["detalle"],
        "total": str(a["total"]) if a["total"] is not None else None,
        "estado": a["estado"], "payload": a["payload"],
    } for a in alertas]
    for i in range(0, len(rows), 200):
        sb.table("alerts").upsert(rows[i:i + 200], on_conflict="company_id,id").execute()
    return len(rows)


def delete_month_alerts(sb: Any, company_id: str, month: str) -> None:
    """Reemplazo por mes: borra las del mes para que reglas retiradas
    no queden como fantasmas (las deterministas se reinsertan)."""
    (sb.table("alerts").delete().eq("company_id", company_id)
     .eq("month", month).execute())


def fetch_snapshot(sb: Any, company_id: str, month: str) -> dict | None:
    res = (sb.table("financial_snapshots").select("*")
           .eq("company_id", company_id).eq("month", month).execute())
    return (res.data or [None])[0]


def fetch_latest_month(sb: Any, company_id: str) -> str | None:
    res = (sb.table("financial_snapshots").select("month")
           .eq("company_id", company_id).order("month", desc=True).limit(1).execute())
    return res.data[0]["month"] if res.data else None


def fetch_alerts(sb: Any, company_id: str, month: str | None = None) -> list[dict]:
    q = (sb.table("alerts").select("*").eq("company_id", company_id)
         .eq("estado", "abierta").order("month", desc=True))
    if month:
        q = q.eq("month", month)
    return q.execute().data or []


def fetch_receivables(sb: Any, company_id: str, abiertas: bool = True) -> list[dict]:
    q = sb.table("accounts_receivable").select("*").eq("company_id", company_id)
    if abiertas:
        q = q.neq("status", "paid")
    return q.order("issued_at").execute().data or []
