"""Repo cobranza: directorio de clientes + acciones de cobranza (T9)."""

from datetime import datetime, timedelta, timezone
from typing import Any

from app.operator.collections import email_valido


def get_contact(sb: Any, company_id: str, customer_rfc: str) -> dict | None:
    res = (sb.table("customer_contacts").select("*")
           .eq("company_id", company_id)
           .eq("customer_rfc", customer_rfc.upper().strip()).execute())
    return (res.data or [None])[0]


def list_contacts(sb: Any, company_id: str) -> list[dict]:
    return (sb.table("customer_contacts").select("*")
            .eq("company_id", company_id).order("customer_name").execute().data or [])


def upsert_contact(sb: Any, company_id: str, customer_rfc: str,
                   email: str, customer_name: str = "",
                   phone: str = "") -> dict:
    rfc = customer_rfc.upper().strip()
    mail = email.strip()
    if not email_valido(mail):
        raise ValueError(f"email inválido: {email!r}")
    row = {"company_id": company_id, "customer_rfc": rfc,
           "customer_name": customer_name, "email": mail, "phone": phone,
           "updated_at": datetime.now(timezone.utc).isoformat()}
    previo = get_contact(sb, company_id, rfc) or {}
    # no pisar nombre/teléfono ya guardados con vacíos (captura solo email)
    if not row["customer_name"]:
        row["customer_name"] = previo.get("customer_name", "")
    if not row["phone"]:
        row["phone"] = previo.get("phone", "")
    (sb.table("customer_contacts")
     .upsert(row, on_conflict="company_id,customer_rfc").execute())
    return get_contact(sb, company_id, rfc) or row


def seed_skeleton(sb: Any, company_id: str, clientes: list[dict]) -> int:
    """Esqueleto del directorio: nombre+RFC sin email (día-1 realista).

    clientes: [{customer_rfc, customer_name, email?}]. Con email solo desde
    seed/private/contacts.json (PII local, nunca en git).
    """
    n = 0
    for c in clientes:
        rfc = c["customer_rfc"].upper().strip()
        previo = get_contact(sb, company_id, rfc) or {}
        # jamás pisar un email capturado con vacío (el seed no manda)
        email = (c.get("email") or "").strip() or (previo.get("email") or None)
        phone = c.get("phone", "") or previo.get("phone", "")
        row = {"company_id": company_id, "customer_rfc": rfc,
               "customer_name": c.get("customer_name", "") or previo.get("customer_name", ""),
               "email": email, "phone": phone}
        (sb.table("customer_contacts")
         .upsert(row, on_conflict="company_id,customer_rfc").execute())
        n += 1
    return n


def enviado_reciente(sb: Any, company_id: str, receivable_id: str,
                     horas: int = 24) -> bool:
    desde = (datetime.now(timezone.utc) - timedelta(hours=horas)).isoformat()
    res = (sb.table("collection_actions").select("id")
           .eq("company_id", company_id).eq("receivable_id", receivable_id)
           .eq("action_type", "email").eq("status", "sent")
           .gte("sent_at", desde).limit(1).execute())
    return bool(res.data)


def record_action(sb: Any, company_id: str, item: dict) -> None:
    (sb.table("collection_actions").insert({
        "company_id": company_id, "receivable_id": item["receivable_id"],
        "action_type": "email", "recipient": item.get("to") or "",
        "subject": item.get("subject") or "", "status": {
            "enviada": "sent", "fallida": "failed", "omitida_24h": "skipped",
        }.get(item.get("status"), "queued"),
        "detail": item.get("detail", "")[:500],
        "sent_at": (datetime.now(timezone.utc).isoformat()
                    if item.get("status") == "enviada" else None),
    }).execute())
    if item.get("status") == "enviada":
        (sb.table("accounts_receivable").update(
            {"last_reminder_at": datetime.now(timezone.utc).isoformat()})
         .eq("company_id", company_id).eq("id", item["receivable_id"]).execute())
