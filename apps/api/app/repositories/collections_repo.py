"""Repo cobranza: directorio de clientes + acciones de cobranza (T9)."""

from datetime import datetime, timedelta, timezone
from typing import Any

from app.operator.collections import email_valido


def get_contact(sb: Any, company_id: str, customer_rfc: str,
                customer_name: str = "") -> dict | None:
    """Resuelve contacto: tupla exacta (rfc, nombre); si hay varios con el
    RFC (XAXX compartido), desempata por nombre; si no, el único."""
    rfc = customer_rfc.upper().strip()
    res = (sb.table("customer_contacts").select("*")
           .eq("company_id", company_id).eq("customer_rfc", rfc).execute())
    filas = res.data or []
    if customer_name:
        for f in filas:
            if (f.get("customer_name") or "") == customer_name:
                return f
    return filas[0] if filas else None


def list_contacts(sb: Any, company_id: str) -> list[dict]:
    return (sb.table("customer_contacts").select("*")
            .eq("company_id", company_id).order("customer_name").execute().data or [])


def resolve(contacts: list[dict], customer_rfc: str,
            customer_name: str = "") -> dict | None:
    """Mejor contacto para (rfc, nombre): tupla exacta, si no el único del
    RFC, si no coincidencia por nombre. None si no hay nada útil."""
    rfc = (customer_rfc or "").upper().strip()
    por_rfc = [c for c in contacts if (c.get("customer_rfc") or "").upper() == rfc]
    if customer_name:
        for c in por_rfc:
            if (c.get("customer_name") or "") == customer_name:
                return c
    if len(por_rfc) == 1:
        return por_rfc[0]
    if customer_name:
        unicos = [c for c in contacts
                  if (c.get("customer_name") or "") == customer_name]
        if len(unicos) == 1:
            return unicos[0]
    return None


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
    previo = get_contact(sb, company_id, rfc, customer_name) or {}
    # no pisar nombre/teléfono ya guardados con vacíos (captura solo email)
    if not row["customer_name"]:
        row["customer_name"] = previo.get("customer_name", "")
    if not row["phone"]:
        row["phone"] = previo.get("phone", "")
    (sb.table("customer_contacts")
     .upsert(row, on_conflict="company_id,customer_rfc,customer_name").execute())
    return get_contact(sb, company_id, rfc, row["customer_name"]) or row


def clear_email(sb: Any, company_id: str, customer_rfc: str,
                customer_name: str = "") -> dict | None:
    """Borra el email del contacto (tupla rfc+nombre por XAXX compartido).
    Conserva la fila del directorio; devuelve el contacto o None."""
    row = get_contact(sb, company_id, customer_rfc, customer_name)
    if not row:
        return None
    (sb.table("customer_contacts").update(
        {"email": None, "updated_at": datetime.now(timezone.utc).isoformat()})
     .eq("company_id", company_id)
     .eq("customer_rfc", row["customer_rfc"])
     .eq("customer_name", row.get("customer_name") or "").execute())
    return get_contact(sb, company_id, customer_rfc, customer_name)


def seed_skeleton(sb: Any, company_id: str, clientes: list[dict]) -> int:
    """Esqueleto del directorio: nombre+RFC sin email (día-1 realista).

    clientes: [{customer_rfc, customer_name, email?}]. Con email solo desde
    seed/private/contacts.json (PII local, nunca en git).
    """
    n = 0
    for c in clientes:
        rfc = c["customer_rfc"].upper().strip()
        previo = get_contact(sb, company_id, rfc, c.get("customer_name", "")) or {}
        # jamás pisar un email capturado con vacío (el seed no manda)
        email = (c.get("email") or "").strip() or (previo.get("email") or None)
        phone = c.get("phone", "") or previo.get("phone", "")
        row = {"company_id": company_id, "customer_rfc": rfc,
               "customer_name": c.get("customer_name", "") or previo.get("customer_name", ""),
               "email": email, "phone": phone}
        (sb.table("customer_contacts")
         .upsert(row, on_conflict="company_id,customer_rfc,customer_name").execute())
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
